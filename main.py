import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import LLMResponse

@register("regex_filter", "LKarxa", "一个使用正则表达式处理LLM消息的插件", "1.2.0", "https://github.com/LKarxa/astrbot_plugin_regex_filter")
class RegexFilterPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.listen_all_responses = self.config.get("listen_all_responses", False)
        
        # 初始化规则列表
        self.rules = []
        
        # 加载替换规则
        replace_rules = self.config.get("replace_rules", [])
        for rule in replace_rules:
            if isinstance(rule, str):
                pattern = rule
                replacement = ""
            else:
                pattern = rule.get("pattern", "") if hasattr(rule, "get") else str(rule)
                replacement = rule.get("replacement", "") if hasattr(rule, "get") else ""
                
            if pattern:
                try:
                    re.compile(pattern)
                    description = f"替换规则: {pattern} -> {replacement}"
                    self.rules.append([pattern, replacement, "replace", description])
                    logger.debug(f"加载替换规则: {pattern} -> {replacement}")
                except re.error as e:
                    logger.warning(f"无效的正则表达式规则: {pattern}, 错误: {str(e)}")
        
        # 加载删除规则
        delete_rules = self.config.get("delete_rules", [])
        for rule in delete_rules:
            if isinstance(rule, str):
                pattern = rule
            else:
                pattern = rule.get("pattern", "") if hasattr(rule, "get") else str(rule)
                
            if pattern:
                try:
                    re.compile(pattern)
                    description = f"删除规则: {pattern}"
                    self.rules.append([pattern, "", "delete", description])
                    logger.debug(f"加载删除规则: {pattern}")
                except re.error as e:
                    logger.warning(f"无效的正则表达式规则: {pattern}, 错误: {str(e)}")
        
        # 如果没有规则，使用默认规则
        if not self.rules:
            self.rules = [
                [r'不可以', r'可以', 'replace', '将"不可以"替换为"可以"'],
                [r'(糟糕|坏|不好)', r'好', 'replace', '将"糟糕"、"坏"或"不好"替换为"好"'],
                [r'问题', r'', 'delete', '删除所有"问题"']
            ]
            
        logger.info(f"RegexFilter插件已加载，规则数量：{len(self.rules)}")

    # 添加规则到配置文件
    def _add_rule_to_config(self, pattern: str, replacement: str, action: str, description: str):
        if not self.config:
            return
            
        # 创建新的规则项
        rule_item = {"pattern": pattern}
        if action != "delete":
            rule_item["replacement"] = replacement
            
        # 根据不同的action添加到不同的规则列表
        if action == "replace":
            rules_key = "replace_rules"
        elif action == "delete":
            rules_key = "delete_rules"
        else:
            logger.warning(f"不支持的规则类型: {action}")
            return
            
        rules = self.config.get(rules_key, [])
        rules.append(rule_item)
        self.config[rules_key] = rules
        self.config.save_config()

    # 从配置文件中删除规则
    def _remove_rule_from_config(self, index: int):
        if not self.config:
            return False
            
        if index < 0 or index >= len(self.rules):
            return False
            
        rule = self.rules[index]
        pattern, _, action, _ = rule
        
        # 根据action确定从哪个列表中删除
        if action == "replace":
            rules_key = "replace_rules"
        elif action == "delete":
            rules_key = "delete_rules"
        else:
            return False
            
        # 查找并删除匹配的规则
        rules = self.config.get(rules_key, [])
        for i, r in enumerate(rules):
            if r.get("pattern") == pattern:
                rules.pop(i)
                self.config[rules_key] = rules
                self.config.save_config()
                return True
                
        return False
        
    # 应用正则规则到文本
    def _apply_rules_to_text(self, text):
        if not text:
            return text, []
            
        modified_text = text
        applied_rules = []
        
        # 应用所有正则规则
        for i, rule in enumerate(self.rules):
            pattern, replacement, action, description = rule
            old_text = modified_text
            
            try:
                if action == 'replace':
                    modified_text = re.sub(pattern, replacement, modified_text)
                elif action == 'delete':
                    modified_text = re.sub(pattern, '', modified_text)
                
                if old_text != modified_text:
                    applied_rules.append(i+1)
                    logger.debug(f"应用规则 {i+1}: {description}")
            except re.error as e:
                logger.warning(f"规则 {i+1} ({pattern}) 应用失败: {str(e)}")
                
        return modified_text, applied_rules

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """监听LLM响应，使用正则表达式进行处理"""
        if not self.enabled:
            return
            
        if resp.completion_text:
            original_text = resp.completion_text
            modified_text, applied_rules = self._apply_rules_to_text(original_text)
            
            # 如果文本已被修改，则更新响应
            if modified_text != original_text:
                resp.completion_text = modified_text
                logger.info(f"正则处理：文本已修改，应用了 {len(applied_rules)} 条规则")

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """监听所有回复消息，使用正则表达式进行处理"""
        logger.debug("on_decorating_result被调用，开始处理消息")
        
        # 如果未启用插件或监听所有回复，则退出
        if not self.enabled or not self.listen_all_responses:
            logger.debug(f"on_decorating_result提前退出：enabled={self.enabled}, listen_all_responses={self.listen_all_responses}")
            return
        
        # 获取回复结果
        result = event.get_result()
        if not result:
            logger.debug("on_decorating_result: 无法获取事件结果，退出处理")
            return
            
        chain = result.chain
        logger.debug(f"on_decorating_result: 获取到消息链类型: {type(chain)}")
        
        # 检查chain是否为list类型
        if not isinstance(chain, list):
            logger.debug(f"on_decorating_result: 消息链不是list类型: {type(chain)}")
            return
        
        # 导入Plain组件类，用于识别纯文本消息
        from astrbot.api.message_components import Plain
        
        # 处理消息链中的Plain文本组件
        modified = False
        for i, component in enumerate(chain):
            # 检查组件是否是Plain类型
            if isinstance(component, Plain):
                original_text = component.text
                logger.debug(f"on_decorating_result: 找到Plain组件，文本: {original_text[:50]}...")
                
                # 应用规则处理文本
                modified_text, applied_rules = self._apply_rules_to_text(original_text)
                
                # 如果文本已被修改，直接更新Plain组件的text属性
                if modified_text != original_text:
                    logger.debug(f"on_decorating_result: 文本已被修改，更新Plain组件")
                    component.text = modified_text
                    modified = True
                    logger.debug(f"on_decorating_result: 应用了{len(applied_rules)}条规则")
        
        # 如果有任何修改，记录日志
        if modified:
            logger.info(f"[所有回复] 正则处理：文本已修改，应用了规则")
        else:
            logger.debug("on_decorating_result: 未修改任何Plain组件")

    @filter.command("regex_add")
    async def add_regex_rule(self, event: AstrMessageEvent, pattern: str, replacement: str = ""):
        """添加正则规则
        - 不提供替换文本时：删除操作 (delete)，如: regex_add 测试
        - 提供替换文本时：替换操作 (replace)，如: regex_add 测试1 测试2
        """
        # 根据参数判断操作类型
        if not pattern:
            yield event.plain_result("参数不足。请使用以下格式：\n"
                                    "- 删除：regex_add 模式\n"
                                    "- 替换：regex_add 模式 替换文本")
            return
        
        # 根据replacement是否为空判断操作类型
        if not replacement:
            action = "delete"
        else:
            action = "replace"
        
        # 尝试编译正则表达式，检查有效性
        try:
            re.compile(pattern)
        except re.error as e:
            yield event.plain_result(f"正则表达式无效: {str(e)}")
            return
        
        # 生成易于理解的描述
        action_desc = '替换' if action == 'replace' else '删除'
        
        if action == 'delete':
            description = f"动态添加的{action_desc}规则: {pattern}"
        else:
            description = f"动态添加的{action_desc}规则: {pattern} -> {replacement}"
        
        # 添加到内存中的规则列表
        self.rules.append([pattern, replacement, action, description])
        
        # 更新配置文件
        self._add_rule_to_config(pattern, replacement, action, description)
            
        yield event.plain_result(f"{action_desc}规则已添加！当前规则数量：{len(self.rules)}")
    
    @filter.command("regex_list")
    async def list_regex_rules(self, event: AstrMessageEvent):
        if not self.rules:
            yield event.plain_result("当前没有规则")
            return
        
        # 按类型分组规则
        replace_rules = []
        delete_rules = []
        
        for i, rule in enumerate(self.rules):
            pattern, replacement, action, description = rule
            rule_info = f"{i+1}. 模式: `{pattern}`"
            if action == "replace":
                rule_info += f" | 替换: `{replacement}`"
            rule_info += f"\n   描述: {description}"
            
            if action == "replace":
                replace_rules.append(rule_info)
            elif action == "delete":
                delete_rules.append(rule_info)
        
        result = "当前的正则表达式规则：\n"
        
        if replace_rules:
            result += "\n替换规则：\n" + "\n".join(replace_rules) + "\n"
        if delete_rules:
            result += "\n删除规则：\n" + "\n".join(delete_rules) + "\n"
            
        yield event.plain_result(result)
    
    @filter.command("regex_remove")
    async def remove_regex_rule(self, event: AstrMessageEvent, index: int):
        if index < 1 or index > len(self.rules):
            yield event.plain_result(f"无效的索引：{index}，有效范围：1-{len(self.rules)}")
            return
        
        # 从内存中移除
        removed_rule = self.rules.pop(index-1)
        
        # 更新配置文件
        self._remove_rule_from_config(index-1)
            
        pattern, replacement, action, description = removed_rule
        yield event.plain_result(f"规则已删除：模式 `{pattern}` | 操作 {action}\n描述: {description}")
    
    @filter.command("regex_test")
    async def test_regex(self, event: AstrMessageEvent, text: str):
        if not self.enabled:
            yield event.plain_result("RegexFilter插件当前已禁用，测试结果不会反映实际运行状态")

        modified_text, applied_rules_indices = self._apply_rules_to_text(text)
        
        result = f"原文本: {text}\n"
        result += f"处理后: {modified_text}\n"
        
        if applied_rules_indices:
            applied_rules = [f"规则 {i}: {self.rules[i-1][3]}" for i in applied_rules_indices]
            result += "应用的规则:\n- " + "\n- ".join(applied_rules)
        else:
            result += "没有规则被应用"
            
        yield event.plain_result(result)
    
    @filter.command("regex_listen_all")
    async def toggle_listen_all(self, event: AstrMessageEvent):
        self.listen_all_responses = not self.listen_all_responses
        
        # 更新配置
        if self.config:
            self.config["listen_all_responses"] = self.listen_all_responses
            self.config.save_config()
            
        status = "开启" if self.listen_all_responses else "关闭"
        yield event.plain_result(f"监听所有回复功能已{status}")
    
    @filter.command("regex_toggle")
    async def toggle_plugin(self, event: AstrMessageEvent):
        self.enabled = not self.enabled
        
        # 更新配置
        if self.config:
            self.config["enabled"] = self.enabled
            self.config.save_config()
            
        status = "已启用" if self.enabled else "已禁用"
        yield event.plain_result(f"RegexFilter插件已{status}")
    
    async def terminate(self):
        """插件被卸载/停用时会调用"""
        logger.info("RegexFilter插件已卸载")