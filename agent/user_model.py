# ============================================================
# UserModel - 用户画像管理
# ============================================================
"""
UserModel负责用户画像管理，跟踪用户的学习进度和能力水平。

职责：
1. 记录用户信息
2. 跟踪技能水平
3. 管理学习历史
4. 提供个性化建议

设计思路：
- 用户画像是实现个性化教学的基础
- 技能水平用枚举和数值共同表示
- 学习历史用于分析进步轨迹
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class UserLevel(Enum):
    """
    用户水平枚举

    划分用户的编程能力等级。
    """
    BEGINNER = "beginner"             # 初学者（刚接触编程）
    JUNIOR = "junior"                # 初级的（能完成简单任务）
    INTERMEDIATE = "intermediate"    # 中级的（能独立完成项目）
    ADVANCED = "advanced"            # 高级的（能处理复杂问题）
    EXPERT = "expert"                # 专家级的（能优化和架构设计）


class SkillCategory(Enum):
    """
    技能分类枚举

    划分不同的编程技能领域。
    """
    ALGORITHM = "algorithm"           # 算法能力
    DATA_STRUCTURE = "data_structure" # 数据结构
    OOP_DESIGN = "oop_design"         # 面向对象设计
    CODE_QUALITY = "code_quality"    # 代码质量
    DEBUGGING = "debugging"          # 调试能力
    SYSTEM_DESIGN = "system_design"  # 系统设计


@dataclass
class SkillProfile:
    """
    技能画像

    记录用户在某个技能领域的详细情况。
    """
    category: SkillCategory           # 技能类别
    level: UserLevel                  # 当前水平
    score: float                      # 具体评分 (0-1)

    # 统计信息
    practice_count: int = 0           # 练习次数
    success_count: int = 0            # 成功次数
    total_duration_minutes: int = 0  # 总练习时长（分钟）

    # 历史记录
    recent_performance: list[float] = field(default_factory=list)  # 最近N次表现
    strength_areas: list[str] = field(default_factory=list)       # 擅长的子领域
    weakness_areas: list[str] = field(default_factory=list)       # 薄弱子领域

    def update_performance(
        self,
        success: bool,
        score: float,
        duration_minutes: int,
    ) -> None:
        """
        更新技能表现

        在完成一个练习后调用，更新技能数据。

        Args:
            success: 是否成功
            score: 评分 (0-1)
            duration_minutes: 用时（分钟）
        """
        self.practice_count += 1
        if success:
            self.success_count += 1
        self.total_duration_minutes += duration_minutes

        # 保持最近10次的记录
        self.recent_performance.append(score)
        if len(self.recent_performance) > 10:
            self.recent_performance.pop(0)

        # 重新计算评分（加权平均）
        if len(self.recent_performance) >= 3:
            recent_avg = sum(self.recent_performance[-3:]) / 3
            self.score = self.score * 0.7 + recent_avg * 0.3

    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.practice_count == 0:
            return 0.0
        return self.success_count / self.practice_count

    @property
    def recent_trend(self) -> str:
        """
        判断最近趋势

        Returns:
            "improving" | "stable" | "declining"
        """
        if len(self.recent_performance) < 3:
            return "stable"

        recent = self.recent_performance[-3:]
        if recent[-1] > recent[0] + 0.1:
            return "improving"
        elif recent[-1] < recent[0] - 0.1:
            return "declining"
        return "stable"


@dataclass
class UserProfile:
    """
    用户画像

    完整的用户信息，包含基本信息和各技能领域的情况。
    """
    user_id: str                       # 用户唯一标识
    username: str                      # 用户名
    email: str | None = None           # 邮箱

    # 能力概览
    overall_level: UserLevel = UserLevel.BEGINNER  # 总体水平
    skills: dict[SkillCategory, SkillProfile] = field(
        default_factory=dict
    )

    # 学习设置
    preferred_mode: str = "algorithm"  # 偏好模式
    preferred_language: str = "python" # 偏好语言
    difficulty_preference: str = "medium"  # 难度偏好

    # 学习历史
    total_sessions: int = 0           # 总训练次数
    total_time_minutes: int = 0       # 总学习时长
    join_date: datetime = field(default_factory=datetime.now)

    # 最近活动
    last_active: datetime | None = None
    recent_weaknesses: list[str] = field(default_factory=list)

    def get_skill(self, category: SkillCategory) -> SkillProfile | None:
        """获取指定技能"""
        return self.skills.get(category)

    def get_or_create_skill(
        self, category: SkillCategory
    ) -> SkillProfile:
        """获取或创建指定技能"""
        if category not in self.skills:
            self.skills[category] = SkillProfile(
                category=category,
                level=UserLevel.BEGINNER,
                score=0.3,
            )
        return self.skills[category]

    def update_overall_level(self) -> None:
        """根据各技能情况更新总体水平"""
        if not self.skills:
            return

        # 计算各技能的平均评分
        avg_score = sum(s.score for s in self.skills.values()) / len(self.skills)

        # 更新总体水平
        if avg_score >= 0.9:
            self.overall_level = UserLevel.EXPERT
        elif avg_score >= 0.75:
            self.overall_level = UserLevel.ADVANCED
        elif avg_score >= 0.5:
            self.overall_level = UserLevel.INTERMEDIATE
        elif avg_score >= 0.25:
            self.overall_level = UserLevel.JUNIOR
        else:
            self.overall_level = UserLevel.BEGINNER


class UserModel(ABC):
    """
    UserModel抽象基类

    定义用户建模功能的通用接口。
    具体的存储和持久化由子类实现。
    """

    @abstractmethod
    async def get_user_profile(self, user_id: str) -> UserProfile | None:
        """
        获取用户画像

        Args:
            user_id: 用户ID

        Returns:
            UserProfile: 用户画像，如果不存在返回None
        """
        pass

    @abstractmethod
    async def save_user_profile(self, profile: UserProfile) -> None:
        """
        保存用户画像

        Args:
            profile: 用户画像
        """
        pass

    @abstractmethod
    async def create_user_profile(
        self, user_id: str, username: str, **kwargs
    ) -> UserProfile:
        """
        创建新用户画像

        Args:
            user_id: 用户ID
            username: 用户名
            **kwargs: 其他初始化参数

        Returns:
            UserProfile: 新创建的用户画像
        """
        pass

    # ============================================================
    # 辅助方法
    # ============================================================

    async def get_user_level(self, user_id: str) -> UserLevel:
        """获取用户水平"""
        profile = await self.get_user_profile(user_id)
        if profile is None:
            return UserLevel.BEGINNER
        return profile.overall_level

    async def update_skill(
        self,
        user_id: str,
        category: SkillCategory,
        success: bool,
        score: float,
        duration_minutes: int,
    ) -> None:
        """
        更新用户技能

        Args:
            user_id: 用户ID
            category: 技能类别
            success: 是否成功
            score: 评分
            duration_minutes: 用时
        """
        profile = await self.get_user_profile(user_id)
        if profile is None:
            return

        skill = profile.get_or_create_skill(category)
        skill.update_performance(success, score, duration_minutes)
        profile.update_overall_level()

        await self.save_user_profile(profile)


# ============================================================
# 内存实现（示例）
# ============================================================

class InMemoryUserModel(UserModel):
    """
    内存用户模型

    简单的内存实现，用于原型开发。
    生产环境应使用数据库实现。
    """

    def __init__(self):
        """初始化内存存储"""
        self._profiles: dict[str, UserProfile] = {}

    async def get_user_profile(self, user_id: str) -> UserProfile | None:
        """获取用户画像"""
        return self._profiles.get(user_id)

    async def save_user_profile(self, profile: UserProfile) -> None:
        """保存用户画像"""
        self._profiles[profile.user_id] = profile

    async def create_user_profile(
        self, user_id: str, username: str, **kwargs
    ) -> UserProfile:
        """创建新用户画像"""
        profile = UserProfile(
            user_id=user_id,
            username=username,
            email=kwargs.get("email"),
            preferred_language=kwargs.get("preferred_language", "python"),
        )
        self._profiles[user_id] = profile
        return profile
