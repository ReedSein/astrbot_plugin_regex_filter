import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import LLMResponse
import astrbot.api.message_components as Comp

@register("regex_filter", "GitHub Copilot", "一个使用正则表达式处理LLM消息的插件", "1.0.0", "https://github.com/yourusername/astrbot_plugin_regex_filter")
class RegexFilterPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}  # 如果没有配置，使用空字典
        self.enabled = self.config.get("enabled", True)
        self.debug_mode = self.config.get("debug_mode", False)
        self.add_end_mark = self.config.get("add_end_mark", True)
        self.end_mark = self.config.get("end_mark", " (已通过正则处理)")
        
        # 从配置中读取各类规则
        self.rules = []
        
        # 加载替换规则 (现在是list格式，每项包含pattern和replacement)
        replace_rules = self.config.get("replace_rules", [])
        for rule in replace_rules:
            # 处理rule可能是字符串的情况
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
                    if self.debug_mode:
                        logger.debug(f"加载替换规则: {pattern} -> {replacement}")
                except re.error as e:
                    logger.warning(f"无效的正则表达式规则: {pattern}, 错误: {str(e)}")
        
        # 加载删除规则 (list格式，每项只包含pattern)
        delete_rules = self.config.get("delete_rules", [])
        for rule in delete_rules:
            # 处理rule可能是字符串的情况
            if isinstance(rule, str):
                pattern = rule
            else:
                pattern = rule.get("pattern", "") if hasattr(rule, "get") else str(rule)
                
            if pattern:
                try:
                    re.compile(pattern)
                    description = f"删除规则: {pattern}"
                    self.rules.append([pattern, "", "delete", description])
                    if self.debug_mode:
                        logger.debug(f"加载删除规则: {pattern}")
                except re.error as e:
                    logger.warning(f"无效的正则表达式规则: {pattern}, 错误: {str(e)}")
        
        # 加载附加规则(后面添加) (list格式，每项包含pattern和replacement)
        append_rules = self.config.get("append_rules", [])
        for rule in append_rules:
            # 处理rule可能是字符串的情况
            if isinstance(rule, str):
                pattern = rule
                replacement = ""
            else:
                pattern = rule.get("pattern", "") if hasattr(rule, "get") else str(rule)
                replacement = rule.get("replacement", "") if hasattr(rule, "get") else ""
                
            if pattern:
                try:
                    re.compile(pattern)
                    description = f"后添加规则: {pattern} -> {replacement}"
                    self.rules.append([pattern, replacement, "append", description])
                    if self.debug_mode:
                        logger.debug(f"加载后添加规则: {pattern} -> {replacement}")
                except re.error as e:
                    logger.warning(f"无效的正则表达式规则: {pattern}, 错误: {str(e)}")
        
        # 加载前置规则(前面添加) (list格式，每项包含pattern和replacement)
        prepend_rules = self.config.get("prepend_rules", [])
        for rule in prepend_rules:
            # 处理rule可能是字符串的情况
            if isinstance(rule, str):
                pattern = rule
                replacement = ""
            else:
                pattern = rule.get("pattern", "") if hasattr(rule, "get") else str(rule)
                replacement = rule.get("replacement", "") if hasattr(rule, "get") else ""
                
            if pattern:
                try:
                    re.compile(pattern)
                    description = f"前添加规则: {pattern} -> {replacement}"
                    self.rules.append([pattern, replacement, "prepend", description])
                    if self.debug_mode:
                        logger.debug(f"加载前添加规则: {pattern} -> {replacement}")
                except re.error as e:
                    logger.warning(f"无效的正则表达式规则: {pattern}, 错误: {str(e)}")
        
        # 如果没有从配置中读取到规则，使用默认规则
        if not self.rules:
            self.rules = [
                [r'不可以', r'可以', 'replace', '将"不可以"替换为"可以"'],
                [r'(糟糕|坏|不好)', r'好', 'replace', '将"糟糕"、"坏"或"不好"替换为"好"'],
                [r'问题', r'', 'delete', '删除所有"问题"'],
                [r'$', r' (已通过正则处理)', 'append', '在消息末尾添加标记'],
            ]
            
        logger.info(f"RegexFilter插件已加载，规则数量：{len(self.rules)}")
        if self.debug_mode:
            for i, rule in enumerate(self.rules):
                pattern, replacement, action, description = rule
                logger.debug(f"规则 {i+1}: {pattern} -> {replacement} ({action}), 描述: {description}")

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
        elif action == "append":
            rules_key = "append_rules"
        elif action == "prepend":
            rules_key = "prepend_rules"
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
        elif action == "append":
            rules_key = "append_rules"
        elif action == "prepend":
            rules_key = "prepend_rules"
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

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """监听LLM响应，使用正则表达式进行处理"""
        if not self.enabled:
            if self.debug_mode:
                logger.debug("RegexFilter插件已禁用，跳过处理")
            return
            
        if resp.completion_text:
            original_text = resp.completion_text
            modified_text = original_text
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
                    elif action == 'append':
                        modified_text = re.sub(pattern, r'\g<0>' + replacement, modified_text)
                    elif action == 'prepend':
                        modified_text = re.sub(pattern, replacement + r'\g<0>', modified_text)
                    
                    if old_text != modified_text:
                        applied_rules.append(i+1)
                        if self.debug_mode:
                            logger.debug(f"应用规则 {i+1}: {description}")
                except re.error as e:
                    logger.warning(f"规则 {i+1} ({pattern}) 应用失败: {str(e)}")
            
            # 如果启用了end_mark且尚未通过规则添加，添加末尾标记
            if self.add_end_mark and not any(r[3] == "在消息末尾添加标记" for r in self.rules if r[0] == '$' and r[2] == 'append'):
                modified_text += self.end_mark
                if self.debug_mode:
                    logger.debug(f"添加末尾标记: {self.end_mark}")
            
            # 如果文本已被修改，则更新响应
            if modified_text != original_text:
                resp.completion_text = modified_text
                if self.debug_mode:
                    logger.debug(f"原文本: {original_text}")
                    logger.debug(f"修改后: {modified_text}")
                    logger.debug(f"应用的规则: {applied_rules}")
                else:
                    logger.info(f"正则处理：文本已修改，应用了 {len(applied_rules)} 条规则")

    @filter.command("regex_add")
    async def add_regex_rule(self, event: AstrMessageEvent, pattern: str, replacement: str, action: str):
        if action not in ['replace', 'delete', 'append', 'prepend']:
            yield event.plain_result(f"不支持的操作类型：{action}，请使用replace/delete/append/prepend之一")
            return
            
        # 尝试编译正则表达式，检查有效性
        try:
            re.compile(pattern)
        except re.error as e:
            yield event.plain_result(f"正则表达式无效: {str(e)}")
            return
        
        # 添加到内存中的规则列表
        description = f"动态添加的规则: {pattern} -> {replacement} ({action})"
        self.rules.append([pattern, replacement, action, description])
        
        # 更新配置文件
        self._add_rule_to_config(pattern, replacement, action, description)
            
        yield event.plain_result(f"规则已添加！当前规则数量：{len(self.rules)}")
    
    @filter.command("regex_list")
    async def list_regex_rules(self, event: AstrMessageEvent):
        if not self.rules:
            yield event.plain_result("当前没有规则")
            return
        
        # 按类型分组规则
        replace_rules = []
        delete_rules = []
        append_rules = []
        prepend_rules = []
        
        for i, rule in enumerate(self.rules):
            pattern, replacement, action, description = rule
            rule_info = f"{i+1}. 模式: `{pattern}`"
            if action != "delete":
                rule_info += f" | 替换: `{replacement}`"
            rule_info += f"\n   描述: {description}"
            
            if action == "replace":
                replace_rules.append(rule_info)
            elif action == "delete":
                delete_rules.append(rule_info)
            elif action == "append":
                append_rules.append(rule_info)
            elif action == "prepend":
                prepend_rules.append(rule_info)
        
        result = "当前的正则表达式规则：\n"
        
        if replace_rules:
            result += "\n替换规则：\n" + "\n".join(replace_rules) + "\n"
        if delete_rules:
            result += "\n删除规则：\n" + "\n".join(delete_rules) + "\n"
        if append_rules:
            result += "\n后添加规则：\n" + "\n".join(append_rules) + "\n"
        if prepend_rules:
            result += "\n前添加规则：\n" + "\n".join(prepend_rules) + "\n"
            
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
        yield event.plain_result(f"规则已删除：模式 `{pattern}` | 替换 `{replacement}` | 操作 {action}\n描述: {description}")
    
    @filter.command("regex_test")
    async def test_regex(self, event: AstrMessageEvent, text: str):
        if not self.enabled:
            yield event.plain_result("RegexFilter插件当前已禁用，测试结果不会反映实际运行状态")

        modified_text = text
        results = []
        
        for i, rule in enumerate(self.rules):
            pattern, replacement, action, description = rule
            old_text = modified_text
            
            try:
                if action == 'replace':
                    modified_text = re.sub(pattern, replacement, modified_text)
                elif action == 'delete':
                    modified_text = re.sub(pattern, '', modified_text)
                elif action == 'append':
                    modified_text = re.sub(pattern, r'\g<0>' + replacement, modified_text)
                elif action == 'prepend':
                    modified_text = re.sub(pattern, replacement + r'\g<0>', modified_text)
                    
                if old_text != modified_text:
                    results.append(f"规则 {i+1}: {description}")
            except re.error as e:
                results.append(f"规则 {i+1} 应用失败: {str(e)}")
        
        # 如果启用了end_mark且尚未通过规则添加，添加末尾标记
        if self.add_end_mark and not any(r[3] == "在消息末尾添加标记" for r in self.rules if r[0] == '$' and r[2] == 'append'):
            modified_text += self.end_mark
            results.append(f"添加末尾标记: {self.end_mark}")
        
        result = f"原文本: {text}\n"
        result += f"处理后: {modified_text}\n"
        if results:
            result += "应用的规则:\n- " + "\n- ".join(results)
        else:
            result += "没有规则被应用"
            
        yield event.plain_result(result)
    
    @filter.command("regex_status")
    async def status(self, event: AstrMessageEvent):
        status = f"RegexFilter插件状态:\n"
        status += f"- 启用状态: {'已启用' if self.enabled else '已禁用'}\n"
        status += f"- 调试模式: {'开启' if self.debug_mode else '关闭'}\n"
        status += f"- 添加末尾标记: {'是' if self.add_end_mark else '否'}"
        if self.add_end_mark:
            status += f"（标记为: {self.end_mark}）\n"
        status += f"- 规则数量: {len(self.rules)}\n"
        
        # 按类型统计规则数量
        replace_count = sum(1 for r in self.rules if r[2] == "replace")
        delete_count = sum(1 for r in self.rules if r[2] == "delete")
        append_count = sum(1 for r in self.rules if r[2] == "append")
        prepend_count = sum(1 for r in self.rules if r[2] == "prepend")
        
        status += f"  - 替换规则: {replace_count}个\n"
        status += f"  - 删除规则: {delete_count}个\n"
        status += f"  - 后添加规则: {append_count}个\n"
        status += f"  - 前添加规则: {prepend_count}个\n"
        
        yield event.plain_result(status)
    
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