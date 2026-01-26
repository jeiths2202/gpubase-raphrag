"""
Permission System
Controls tool access for agents and users.
"""
from typing import Dict, List, Optional, Set
import logging
import fnmatch

from .types import AgentType, PermissionAction, PermissionRule, AgentPermissions

logger = logging.getLogger(__name__)


# Default permissions per agent type
DEFAULT_AGENT_PERMISSIONS: Dict[AgentType, AgentPermissions] = {
    AgentType.RAG: AgentPermissions(
        agent_type=AgentType.RAG,
        rules=[
            PermissionRule(tool="vector_search", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="graph_query", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="document_read", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="*", pattern="*", action=PermissionAction.DENY),
        ],
        default_action=PermissionAction.DENY
    ),
    AgentType.IMS: AgentPermissions(
        agent_type=AgentType.IMS,
        rules=[
            PermissionRule(tool="ims_search", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="web_fetch", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="vector_search", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="*", pattern="*", action=PermissionAction.DENY),
        ],
        default_action=PermissionAction.DENY
    ),
    AgentType.VISION: AgentPermissions(
        agent_type=AgentType.VISION,
        rules=[
            PermissionRule(tool="document_read", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="vector_search", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="*", pattern="*", action=PermissionAction.DENY),
        ],
        default_action=PermissionAction.DENY
    ),
    AgentType.CODE: AgentPermissions(
        agent_type=AgentType.CODE,
        rules=[
            PermissionRule(tool="document_read", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="vector_search", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="bash", pattern="*.py", action=PermissionAction.ALLOW),
            PermissionRule(tool="bash", pattern="python*", action=PermissionAction.ALLOW),
            PermissionRule(tool="bash", pattern="npm*", action=PermissionAction.ALLOW),
            PermissionRule(tool="bash", pattern="node*", action=PermissionAction.ALLOW),
            PermissionRule(tool="*", pattern="*", action=PermissionAction.DENY),
        ],
        default_action=PermissionAction.DENY
    ),
    AgentType.PLANNER: AgentPermissions(
        agent_type=AgentType.PLANNER,
        rules=[
            PermissionRule(tool="vector_search", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="graph_query", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="ims_search", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="document_read", pattern="*", action=PermissionAction.ALLOW),
            PermissionRule(tool="*", pattern="*", action=PermissionAction.DENY),
        ],
        default_action=PermissionAction.DENY
    ),
}


class PermissionManager:
    """
    Manages permissions for agent tool access.
    Singleton pattern.
    """

    _instance: Optional['PermissionManager'] = None

    def __init__(self):
        self._agent_permissions: Dict[AgentType, AgentPermissions] = DEFAULT_AGENT_PERMISSIONS.copy()
        self._user_overrides: Dict[str, Dict[str, PermissionAction]] = {}
        self._admin_users: Set[str] = set()

    @classmethod
    def get_instance(cls) -> 'PermissionManager':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_agent_permissions(
        self,
        agent_type: AgentType,
        permissions: AgentPermissions
    ) -> None:
        """Set permissions for an agent type"""
        self._agent_permissions[agent_type] = permissions

    def add_admin_user(self, user_id: str) -> None:
        """Add a user as admin (can use any tool)"""
        self._admin_users.add(user_id)

    def remove_admin_user(self, user_id: str) -> None:
        """Remove admin status from user"""
        self._admin_users.discard(user_id)

    def set_user_override(
        self,
        user_id: str,
        tool: str,
        action: PermissionAction
    ) -> None:
        """Set a per-user permission override"""
        if user_id not in self._user_overrides:
            self._user_overrides[user_id] = {}
        self._user_overrides[user_id][tool] = action

    def check_permission(
        self,
        tool: str,
        agent_type: AgentType,
        user_id: Optional[str] = None,
        resource: str = "*"
    ) -> bool:
        """
        Check if a tool is allowed for an agent/user combination.

        Args:
            tool: Tool name to check
            agent_type: Type of agent requesting
            user_id: Optional user ID for per-user overrides
            resource: Optional resource pattern (for file-based permissions)

        Returns:
            True if allowed, False otherwise
        """
        # Admin users can do anything
        if user_id and user_id in self._admin_users:
            return True

        # Check user overrides first
        if user_id and user_id in self._user_overrides:
            user_rules = self._user_overrides[user_id]
            if tool in user_rules:
                return user_rules[tool] == PermissionAction.ALLOW

        # Check agent permissions
        agent_perms = self._agent_permissions.get(agent_type)
        if agent_perms is None:
            return False

        # Find matching rule
        for rule in agent_perms.rules:
            if self._matches_rule(rule, tool, resource):
                if rule.action == PermissionAction.ALLOW:
                    return True
                elif rule.action == PermissionAction.DENY:
                    return False
                # ASK action - for now treat as deny
                # In future could prompt user
                return False

        # Default action
        return agent_perms.default_action == PermissionAction.ALLOW

    def _matches_rule(
        self,
        rule: PermissionRule,
        tool: str,
        resource: str
    ) -> bool:
        """Check if a rule matches the tool and resource"""
        # Check tool match
        if rule.tool != "*" and rule.tool != tool:
            return False

        # Check resource pattern match
        if rule.pattern != "*":
            if not fnmatch.fnmatch(resource, rule.pattern):
                return False

        return True

    def get_allowed_tools(
        self,
        agent_type: AgentType,
        user_id: Optional[str] = None
    ) -> List[str]:
        """Get list of allowed tools for an agent/user"""
        agent_perms = self._agent_permissions.get(agent_type)
        if agent_perms is None:
            return []

        allowed = set()
        for rule in agent_perms.rules:
            if rule.action == PermissionAction.ALLOW and rule.tool != "*":
                allowed.add(rule.tool)

        # Apply user overrides
        if user_id and user_id in self._user_overrides:
            for tool, action in self._user_overrides[user_id].items():
                if action == PermissionAction.ALLOW:
                    allowed.add(tool)
                elif action == PermissionAction.DENY:
                    allowed.discard(tool)

        return list(allowed)

    def get_permissions_info(
        self,
        agent_type: AgentType
    ) -> Dict:
        """Get permission info for debugging"""
        agent_perms = self._agent_permissions.get(agent_type)
        if agent_perms is None:
            return {"error": f"No permissions for {agent_type}"}

        return {
            "agent_type": agent_type.value,
            "default_action": agent_perms.default_action.value,
            "rules": [
                {
                    "tool": r.tool,
                    "pattern": r.pattern,
                    "action": r.action.value,
                    "description": r.description
                }
                for r in agent_perms.rules
            ]
        }


# Convenience function
def get_permission_manager() -> PermissionManager:
    """Get the global permission manager"""
    return PermissionManager.get_instance()
