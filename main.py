import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import LLMResponse
from astrbot.api.message_components import Plain

@dataclass
class RegexRule:
    """
    正则表达式规则的数据类
    """
    compiled_pattern: re.Pattern  # 预编译的正则对象，用于高性能匹配
    raw_pattern: str              # 原始正则字符串，用于展示和保存
    replacement: str              # 替换文本
    action: str                   # 动作类型: 'replace' 或 'delete'
    description: str              # 规则描述

@register("regex_filter", "LKarxa", "一个使用正则表达式处理LLM消息的插件", "1.3.0", "https://github.com/LKarxa/astrbot_plugin_regex_filter")
class RegexFilterPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        """
        插件初始化
        """
        super().__init__(context)
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.listen_all_responses = self.config.get("listen_all_responses", False)
        
        # 使用强类型的列表存储规则，而非原来的 list of list
        self.rules: List[RegexRule] = []
        
        # 加载规则
        self._load_rules_from_config()

    def _load_rules_from_config(self):
        """从配置中加载并编译规则"""
        self.rules.clear()
        
        # 加载替换规则
        replace_rules = self.config.get("replace_rules", [])
        for rule in replace_rules:
            self._compile_and_add_memory(
                pattern=rule.get("pattern", ""),
                replacement=rule.get("replacement", ""),
                action="replace"
            )
            
        # 加载删除规则
        delete_rules = self.config.get("delete_rules", [])
        for rule in delete_rules:
            self._compile_and_add_memory(
                pattern=rule.get("pattern", ""),
                replacement="",
                action="delete"
            )
            
        logger.info(f"RegexFilter插件已加载，当前生效规则数: {len(self.rules)}")

    def _compile_and_add_memory(self, pattern: str, replacement: str, action: str) -> bool:
        """
        编译正则并添加到内存列表中 (不涉及文件保存)
        返回: 是否成功添加
        """
        if not pattern:
            return False
            
        try:
            # 核心优化：预编译正则表达式
            compiled = re.compile(pattern)
            
            desc = f"{'替换' if action == 'replace' else '删除'}规则: {pattern}" + (f" -> {replacement}" if action == 'replace' else "")
            
            rule_obj = RegexRule(
                compiled_pattern=compiled,
                raw_pattern=pattern,
                replacement=replacement,
                action=action,
                description=desc
            )
            self.rules.append(rule_obj)
            return True
        except re.error as e:
            logger.warning(f"规则编译失败 (pattern: {pattern}): {str(e)}")
            return False

    def _sync_rules_to_config(self):
        """
        将内存中的规则全量同步保存到配置文件。
        Single Source of Truth: 内存是主态，配置是持久化层。
        """
        replace_list = []
        delete_list = []
        
        for rule in self.rules:
            item = {"pattern": rule.raw_pattern}
            if rule.action == "replace":
                item["replacement"] = rule.replacement
                replace_list.append(item)
            else:
                # delete
                delete_list.append(item)
                
        # 更新 config 对象
        self.config["replace_rules"] = replace_list
        self.config["delete_rules"] = delete_list
        
        # 持久化保存
        self.config.save_config()
        logger.info("规则已同步保存到配置文件")

    def _apply_rules_to_text(self, text: str) -> Tuple[str, List[int]]:
        """
        应用所有内存中的规则到指定文本
        返回: (修改后的文本, 应用的规则索引列表)
        """
        if not text:
            return text, []
            
        modified_text = text
        applied_rules_indices = []
        
        for i, rule in enumerate(self.rules):
            old_text = modified_text
            
            try:
                # 核心优化：直接使用预编译对象的 sub 方法
                if rule.action == 'replace':
                    modified_text = rule.compiled_pattern.sub(rule.replacement, modified_text)
                elif rule.action == 'delete':
                    modified_text = rule.compiled_pattern.sub('', modified_text)
                
                if old_text != modified_text:
                    applied_rules_indices.append(i + 1)
                    logger.debug(f"应用规则 {i+1}: {rule.description}")
            except Exception as e:
                logger.warning(f"规则 {i+1} 执行异常: {e}")
                
        return modified_text, applied_rules_indices

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """监听LLM响应"""
        if not self.enabled:
            return
            
        if resp.completion_text:
            original_text = resp.completion_text
            modified_text, applied_rules = self._apply_rules_to_text(original_text)
            
            if modified_text != original_text:
                resp.completion_text = modified_text
                logger.info(f"正则处理LLM响应：应用了 {len(applied_rules)} 条规则")

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """监听所有机器人回复消息"""
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
        
        # 1. 添加到内存
        success = self._compile_and_add_memory(pattern, replacement, action)
        
        if success:
            # 2. 同步到配置
            self._sync_rules_to_config()
            
            action_desc = '替换' if action == 'replace' else '删除'
            # 获取刚刚添加的规则描述
            new_rule = self.rules[-1]
            yield event.plain_result(f"✅ {action_desc}规则已添加！\n{new_rule.description}\n当前规则总数：{len(self.rules)}")
        else:
            yield event.plain_result("❌ 规则添加失败，请查看后台日志。")
    
    @filter.command("regex_list")
    async def list_regex_rules(self, event: AstrMessageEvent):
        """显示当前所有规则"""
        if not self.rules:
            yield event.plain_result("当前没有已配置的规则。请使用 /regex_add 添加。")
            return
        
        replace_rules_text = []
        delete_rules_text = []
        
        for i, rule in enumerate(self.rules):
            # 使用 dataclass 属性访问，更清晰
            rule_info = f"{i+1}. `{rule.raw_pattern}`"
            
            if rule.action == "replace":
                rule_info += f" -> `{rule.replacement}`"
                replace_rules_text.append(rule_info)
            else:
                delete_rules_text.append(rule_info)
        
        result = "📋 当前正则表达式规则：\n"
        if replace_rules_text:
            result += "\n--- 🔄 替换规则 ---\n" + "\n".join(replace_rules_text)
        if delete_rules_text:
            result += "\n--- 🗑️ 删除规则 ---\n" + "\n".join(delete_rules_text)
            
        yield event.plain_result(result)
    
    @filter.command("regex_remove")
    async def remove_regex_rule(self, event: AstrMessageEvent, index: int):
        """按索引删除规则"""
        if not (1 <= index <= len(self.rules)):
            yield event.plain_result(f"无效的索引：{index}。有效范围是 1 到 {len(self.rules)}。")
            return
        
        # 1. 从内存移除
        removed_rule = self.rules.pop(index - 1)
        
        # 2. 同步到配置
        self._sync_rules_to_config()
        
        yield event.plain_result(f"🗑️ 规则 {index} 已删除。\n详情: {removed_rule.description}")
    
    @filter.command("regex_test")
    async def test_regex(self, event: AstrMessageEvent, text: str):
        """测试当前规则对文本的处理效果"""
        if not self.enabled:
            yield event.plain_result("⚠️ 插件当前已禁用，测试结果可能不反映实际运行状态。")

        modified_text, applied_rules_indices = self._apply_rules_to_text(text)
        
        result = f"🧪 **测试结果**\n"
        result += f"**原文本**: {text}\n"
        result += f"**处理后**: {modified_text}\n"
        
        if applied_rules_indices:
            # 更加清晰的规则引用
            applied_rules_desc = [f"规则 {i}: {self.rules[i-1].description}" for i in applied_rules_indices]
            result += "\n**✅ 应用的规则**:\n- " + "\n- ".join(applied_rules_desc)
        else:
            result += "\n无规则被应用。"
            
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
