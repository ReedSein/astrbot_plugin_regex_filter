import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import LLMResponse
from astrbot.api.message_components import Plain

@register("regex_filter", "LKarxa", "一个使用正则表达式处理LLM消息的插件", "1.3.0", "https://github.com/LKarxa/astrbot_plugin_regex_filter")
class RegexFilterPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        """
        插件初始化。
        此方法现在完全依赖于 AstrBot 的配置系统。
        初始默认规则在 `_conf_schema.json` 中定义，
        AstrBot 框架会在首次加载时自动用它们生成配置文件。
        """
        super().__init__(context)
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.listen_all_responses = self.config.get("listen_all_responses", False)
        
        # 初始化内存中的规则列表
        self.rules = []
        
        # 从用户配置加载替换规则
        # self.config.get 会从 config.json 读取，如果文件不存在，则从 _conf_schema.json 的 default 值读取
        replace_rules = self.config.get("replace_rules", [])
        for rule in replace_rules:
            # 配置中的规则现在是结构化的字典
            pattern = rule.get("pattern", "")
            replacement = rule.get("replacement", "")
                
            if pattern:
                try:
                    re.compile(pattern)
                    description = f"替换规则: {pattern} -> {replacement}"
                    self.rules.append([pattern, replacement, "replace", description])
                    logger.debug(f"加载替换规则: {pattern} -> {replacement}")
                except re.error as e:
                    logger.warning(f"从配置加载替换规则失败 (pattern: {pattern}): {str(e)}")
        
        # 从用户配置加载删除规则
        delete_rules = self.config.get("delete_rules", [])
        for rule in delete_rules:
            pattern = rule.get("pattern", "")
                
            if pattern:
                try:
                    re.compile(pattern)
                    description = f"删除规则: {pattern}"
                    self.rules.append([pattern, "", "delete", description])
                    logger.debug(f"加载删除规则: {pattern}")
                except re.error as e:
                    logger.warning(f"从配置加载删除规则失败 (pattern: {pattern}): {str(e)}")
        
        logger.info(f"RegexFilter插件已加载，从配置中加载了 {len(self.rules)} 条规则。")

    def _add_rule_to_config(self, pattern: str, replacement: str, action: str):
        """将规则以字典形式添加到配置文件并保存"""
        if not self.config:
            logger.error("配置对象为空，无法保存规则")
            return

        try:
            rule_item = {"pattern": pattern}
            if action == "replace":
                rule_item["replacement"] = replacement
                rules_key = "replace_rules"
            elif action == "delete":
                rules_key = "delete_rules"
            else:
                logger.warning(f"不支持的规则类型: {action}")
                return
                
            rules = self.config.get(rules_key, [])
            if not isinstance(rules, list):
                logger.warning(f"{rules_key}不是列表类型，重置为空列表")
                rules = []
                
            rules.append(rule_item)
            self.config[rules_key] = rules
            
            self.config.save_config()
            logger.info(f"规则已保存到配置文件，{action}规则: {pattern}")
        except Exception as e:
            logger.error(f"添加规则到配置文件时发生错误: {str(e)}")

    def _remove_rule_from_config(self, rule_to_remove: list):
        """从配置文件中删除指定的规则"""
        if not self.config:
            logger.error("配置对象为空，无法删除规则")
            return False
            
        try:
            pattern, replacement, action, _ = rule_to_remove
            
            if action == "replace":
                rules_key = "replace_rules"
            elif action == "delete":
                rules_key = "delete_rules"
            else:
                logger.error(f"不支持的规则类型: {action}")
                return False
                
            rules = self.config.get(rules_key, [])
            if not isinstance(rules, list):
                logger.warning(f"{rules_key}不是列表类型，无法删除规则")
                return False
                
            found = False
            # 遍历查找要移除的精确规则
            for i, r in enumerate(rules):
                if isinstance(r, dict) and r.get("pattern") == pattern:
                    if action == "replace":
                        if r.get("replacement") == replacement:
                            rules.pop(i)
                            found = True
                            break
                    else: # delete action
                        rules.pop(i)
                        found = True
                        break
                    
            if not found:
                logger.warning(f"在配置文件中未找到规则: {pattern}")
                return False
                
            self.config[rules_key] = rules
            self.config.save_config()
            logger.info(f"规则已从配置文件中删除: {pattern}")
            return True
        except Exception as e:
            logger.error(f"从配置文件中删除规则时发生错误: {str(e)}")
            return False
        
    def _apply_rules_to_text(self, text):
        """应用所有内存中的规则到指定文本"""
        if not text:
            return text, []
            
        modified_text = text
        applied_rules = []
        
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
            
            if modified_text != original_text:
                resp.completion_text = modified_text
                logger.info(f"正则处理LLM响应：文本已修改，应用了 {len(applied_rules)} 条规则")

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """监听所有机器人回复消息，使用正则表达式进行处理"""
        if not self.enabled or not self.listen_all_responses:
            return
        
        result = event.get_result()
        if not result or not result.chain:
            return
            
        chain = result.chain
        if not isinstance(chain, list):
            return
        
        modified = False
        for component in chain:
            if isinstance(component, Plain):
                original_text = component.text
                modified_text, _ = self._apply_rules_to_text(original_text)
                
                if modified_text != original_text:
                    component.text = modified_text
                    modified = True
        
        if modified:
            logger.info(f"[所有回复] 正则处理：消息链中的文本已修改")

    @filter.command("regex_add")
    async def add_regex_rule(self, event: AstrMessageEvent, pattern: str, replacement: str = ""):
        """添加正则规则"""
        if not pattern:
            yield event.plain_result("参数不足。请使用格式：\n- 删除: /regex_add <模式>\n- 替换: /regex_add <模式> <替换文本>")
            return
        
        try:
            re.compile(pattern)
        except re.error as e:
            yield event.plain_result(f"正则表达式无效: {str(e)}")
            return
        
        action = "replace" if replacement else "delete"
        action_desc = '替换' if action == 'replace' else '删除'
        description = f"{action_desc}规则: {pattern}" + (f" -> {replacement}" if action == 'replace' else "")
        
        # 添加到内存
        self.rules.append([pattern, replacement, action, description])
        # 添加到配置文件
        self._add_rule_to_config(pattern, replacement, action)
            
        yield event.plain_result(f"{action_desc}规则已添加！当前规则数量：{len(self.rules)}")
    
    @filter.command("regex_list")
    async def list_regex_rules(self, event: AstrMessageEvent):
        """显示当前所有规则"""
        if not self.rules:
            yield event.plain_result("当前没有已配置的规则。请在WebUI设置或使用 /regex_add 添加。")
            return
        
        replace_rules_text = []
        delete_rules_text = []
        
        for i, (pattern, replacement, action, _) in enumerate(self.rules):
            rule_info = f"{i+1}. 模式: `{pattern}`"
            if action == "replace":
                rule_info += f" | 替换为: `{replacement}`"
                replace_rules_text.append(rule_info)
            else:
                delete_rules_text.append(rule_info)
        
        result = "当前的正则表达式规则：\n"
        if replace_rules_text:
            result += "\n--- 替换规则 ---\n" + "\n".join(replace_rules_text)
        if delete_rules_text:
            result += "\n--- 删除规则 ---\n" + "\n".join(delete_rules_text)
            
        yield event.plain_result(result)
    
    @filter.command("regex_remove")
    async def remove_regex_rule(self, event: AstrMessageEvent, index: int):
        """按索引删除规则"""
        if not (1 <= index <= len(self.rules)):
            yield event.plain_result(f"无效的索引：{index}。有效范围是 1 到 {len(self.rules)}。")
            return
        
        rule_to_remove = self.rules[index-1]

        if self._remove_rule_from_config(rule_to_remove):
            self.rules.pop(index-1)
            pattern, _, action, _ = rule_to_remove
            yield event.plain_result(f"规则 {index} 已成功删除 (模式: `{pattern}`, 操作: {action})。")
        else:
            yield event.plain_result(f"从配置文件中删除规则 {index} 失败，请检查日志。内存中的规则列表可能与配置文件不一致。")
    
    @filter.command("regex_test")
    async def test_regex(self, event: AstrMessageEvent, text: str):
        """测试当前规则对文本的处理效果"""
        if not self.enabled:
            yield event.plain_result("插件当前已禁用，测试结果可能不反映实际运行状态。")

        modified_text, applied_rules_indices = self._apply_rules_to_text(text)
        
        result = f"**测试结果**\n"
        result += f"**原文本**: {text}\n"
        result += f"**处理后**: {modified_text}\n"
        
        if applied_rules_indices:
            applied_rules_desc = [f"规则 {i}: {self.rules[i-1][3]}" for i in applied_rules_indices]
            result += "\n**应用的规则**:\n- " + "\n- ".join(applied_rules_desc)
        else:
            result += "\n没有规则被应用。"
            
        yield event.plain_result(result)
    
    @filter.command("regex_listen_all")
    async def toggle_listen_all(self, event: AstrMessageEvent):
        """切换是否监听所有机器人回复"""
        self.listen_all_responses = not self.listen_all_responses
        
        if self.config:
            self.config["listen_all_responses"] = self.listen_all_responses
            self.config.save_config()
            
        status = "开启" if self.listen_all_responses else "关闭"
        yield event.plain_result(f"监听所有回复功能已{status}。")
    
    @filter.command("regex_toggle")
    async def toggle_plugin(self, event: AstrMessageEvent):
        """切换插件启用/禁用状态"""
        self.enabled = not self.enabled
        
        if self.config:
            self.config["enabled"] = self.enabled
            self.config.save_config()
            
        status = "启用" if self.enabled else "禁用"
        yield event.plain_result(f"RegexFilter插件已{status}。")
    
    async def terminate(self):
        """插件被卸载/停用时调用"""
        logger.info("RegexFilter插件已卸载。")