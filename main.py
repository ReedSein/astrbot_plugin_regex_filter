import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import LLMResponse

@register("regex_filter", "LKarxa", "一个使用正则表达式处理LLM消息的插件", "1.3.0", "https://github.com/LKarxa/astrbot_plugin_regex_filter")
class RegexFilterPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.listen_all_responses = self.config.get("listen_all_responses", False)
        
        # 初始化规则列表
        self.rules = []
        
        # 标志位，用于判断是否加载了默认规则
        default_rules_loaded = False
        
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
        
        # 如果配置文件中没有规则，则使用并保存新的默认规则
        if not self.rules:
            logger.info("未找到任何规则，正在加载并保存新的默认规则...")
            default_rules_loaded = True
            self.rules = [
                # 你指定的新规则列表
                [r'王洪文', r'小王', 'replace', '将"王洪文"替换为"小王"'],
                [r'张春桥', r'春桥', 'replace', '将"张春桥"替换为"春桥"'],
                [r'江青', r'云鹤', 'replace', '将"江青"替换为"云鹤"'],
                [r'华国锋', r'🌸', 'replace', '将"华国锋"替换为"🌸"'],
                [r'immutable', r'うむ', 'replace', '将"immutable"替换为"うむ"'],
                [r'哦？', r'ほう？', 'replace', '将"哦？"替换为"ほう？"'],
                [r'毛泽东', r'🐱', 'replace', '将"毛泽东"替换为"🐱"'],
                [r'叶剑英', r'🥥', 'replace', '将"叶剑英"替换为"🥥"'],
                [r'邓小平', r'总设计师', 'replace', '将"邓小平"替换为"总设计师"'],
                [r'江泽民', r'🐸', 'replace', '将"江泽民"替换为"🐸"'],
                [r'胡锦涛', r'胡桃', 'replace', '将"胡锦涛"替换为"胡桃"'],
                [r'习近平', r'🐻', 'replace', '将"习近平"替换为"🐻"'],
                [r'四人帮', r'f4', 'replace', '将"四人帮"替换为"f4"'],
                [r'文革', r'wegame', 'replace', '将"文革"替换为"wegame"'],
                [r'呵，', r'', 'delete', '删除所有"呵，"']
            ]
            
            # 将默认规则同步到 config 对象中
            config_replace_rules = []
            config_delete_rules = []
            for pattern, replacement, action, _ in self.rules:
                if action == "replace":
                    config_replace_rules.append({"pattern": pattern, "replacement": replacement})
                elif action == "delete":
                    config_delete_rules.append({"pattern": pattern})
            
            self.config["replace_rules"] = config_replace_rules
            self.config["delete_rules"] = config_delete_rules
        
        logger.info(f"RegexFilter插件已加载，规则数量：{len(self.rules)}")

        # 如果加载了默认规则，则执行一次保存操作
        if default_rules_loaded:
            try:
                self.config.save_config()
                logger.info("默认规则已成功保存到配置文件。")
            except Exception as e:
                logger.error(f"保存默认规则到配置文件时失败: {str(e)}")

    # 添加规则到配置文件
    def _add_rule_to_config(self, pattern: str, replacement: str, action: str, description: str):
        if not self.config:
            logger.error("配置对象为空，无法保存规则")
            return
            
        try:
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
                
            # 确保配置中有对应的规则列表
            rules = self.config.get(rules_key, [])
            if not isinstance(rules, list):
                logger.warning(f"{rules_key}不是列表类型，重置为空列表")
                rules = []
                
            rules.append(rule_item)
            self.config[rules_key] = rules
            
            # 保存配置文件
            logger.debug(f"正在保存配置文件，规则数量: {len(rules)}")
            try:
                self.config.save_config()
                logger.info(f"规则已保存到配置文件，{action}规则: {pattern}")
            except Exception as e:
                logger.error(f"保存配置文件失败: {str(e)}")
        except Exception as e:
            logger.error(f"添加规则到配置文件时发生错误: {str(e)}")

    # 从配置文件中删除规则
    def _remove_rule_from_config(self, rule_to_remove: list):
        if not self.config:
            logger.error("配置对象为空，无法删除规则")
            return False
            
        try:
            pattern, _, action, _ = rule_to_remove
            
            # 根据action确定从哪个列表中删除
            if action == "replace":
                rules_key = "replace_rules"
            elif action == "delete":
                rules_key = "delete_rules"
            else:
                logger.error(f"不支持的规则类型: {action}")
                return False
                
            # 查找并删除匹配的规则
            rules = self.config.get(rules_key, [])
            if not isinstance(rules, list):
                logger.warning(f"{rules_key}不是列表类型，无法删除规则")
                return False
                
            found = False
            # 这样可以处理可能存在的重复模式
            for i, r in enumerate(rules):
                if isinstance(r, dict) and r.get("pattern") == pattern:
                    # 对于替换规则，额外检查替换内容以确保精确匹配
                    if action == "replace":
                        if r.get("replacement") == rule_to_remove[1]:
                            rules.pop(i)
                            found = True
                            break
                    else: # 对于删除规则，只匹配模式就足够了
                        rules.pop(i)
                        found = True
                        break
                    
            if not found:
                logger.warning(f"在配置文件中未找到规则: {pattern}")
                return False
                
            # 更新配置并保存
            self.config[rules_key] = rules
            
            try:
                self.config.save_config()
                logger.info(f"规则已从配置文件中删除: {pattern}")
                return True
            except Exception as e:
                logger.error(f"保存配置文件失败: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"从配置文件中删除规则时发生错误: {str(e)}")
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
            description = f"{action_desc}规则: {pattern}"
        else:
            description = f"{action_desc}规则: {pattern} -> {replacement}"
        
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
        
        rule_to_remove = self.rules[index-1]

        # 第一步：尝试从配置文件中删除
        if self._remove_rule_from_config(rule_to_remove):
            # 如果配置文件删除成功，再从内存列表中删除
            self.rules.pop(index-1)
            
            pattern, replacement, action, description = rule_to_remove
            yield event.plain_result(f"规则已删除：模式 `{pattern}` | 操作 {action}\n描述: {description}")
        else:
            # 如果配置文件删除失败，则报告错误，并且不修改内存列表
            yield event.plain_result(f"从配置文件中删除规则失败，请检查日志。")
    
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