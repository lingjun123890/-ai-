import random
from typing import List, Optional

from .card import (Card, AttackCard, ThoughtStampCard, StellarHydrogenCard,
                   SophonPlunderCard, DarkForestStrikeCard,
                   HealCard, DehydrationCard, BunkerPlanCard,
                   DropletImpactCard, StaircasePlanCard,
                   RedCoastCard, TechExplosionCard,
                   ResourceConvertCard, DimensionCleanupCard,
                   WallFacingCard, EscapismCard,
                   SuspicionChainCard, GravityWaveCard,
                   DeterrenceEraCard)
from .config import (BASIC_ATTACK_COUNT,
                     THOUGHT_STAMP_COUNT, STELLAR_HYDROGEN_COUNT,
                     PROTON_SOPHON_COUNT, DARK_FOREST_COUNT,
                     BASIC_HEAL_COUNT,
                     DEHYDRATION_COUNT, BUNKER_PLAN_COUNT,
                     DROPLET_IMPACT_COUNT, STAIRCASE_PLAN_COUNT,
                     RED_COAST_COUNT, TECH_EXPLOSION_COUNT,
                     RESOURCE_CONVERT_COUNT, DIMENSION_CLEANUP_COUNT,
                     WALL_FACING_COUNT, ESCAPISM_COUNT,
                     SUSPICION_CHAIN_COUNT, GRAVITY_WAVE_COUNT,
                     DETERRENCE_ERA_COUNT)


def _scaled(n: int, scale: float) -> int:
    return max(1, int(n * scale)) if scale < 1.0 else n


def build_solo_probability_table() -> tuple:
    """按单挑 scale=0.5 的百分占比, 构建带权随机表。"""
    entries = [
        (AttackCard, "攻击"),
        (ThoughtStampCard, "思想钢印"),
        (StellarHydrogenCard, "恒星级氢弹"),
        (SophonPlunderCard, "智子掠夺"),
        (DarkForestStrikeCard, "黑暗森林打击"),
        (HealCard, "恢复"),
        (DehydrationCard, "脱水"),
        (BunkerPlanCard, "掩体计划"),
        (DropletImpactCard, "水滴撞击"),
        (StaircasePlanCard, "阶梯计划"),
        (RedCoastCard, "红岸监听"),
        (TechExplosionCard, "技术爆炸"),
        (ResourceConvertCard, "资源转化"),
        (DimensionCleanupCard, "降维清理"),
        (WallFacingCard, "面壁计划"),
        (EscapismCard, "逃亡主义"),
        (SuspicionChainCard, "猜疑链"),
        (GravityWaveCard, "引力波天线"),
        (DeterrenceEraCard, "威慑纪元"),
    ]
    raw_counts = [
        BASIC_ATTACK_COUNT,
        THOUGHT_STAMP_COUNT,
        STELLAR_HYDROGEN_COUNT,
        PROTON_SOPHON_COUNT,
        DARK_FOREST_COUNT,
        BASIC_HEAL_COUNT,
        DEHYDRATION_COUNT,
        BUNKER_PLAN_COUNT,
        DROPLET_IMPACT_COUNT,
        STAIRCASE_PLAN_COUNT,
        RED_COAST_COUNT,
        TECH_EXPLOSION_COUNT,
        RESOURCE_CONVERT_COUNT,
        DIMENSION_CLEANUP_COUNT,
        WALL_FACING_COUNT,
        ESCAPISM_COUNT,
        SUSPICION_CHAIN_COUNT,
        GRAVITY_WAVE_COUNT,
        DETERRENCE_ERA_COUNT,
    ]
    weights = [_scaled(n, 0.5) for n in raw_counts]
    total = sum(weights)
    probs = [w / total for w in weights]
    cumulative = []
    acc = 0.0
    for p in probs:
        acc += p
        cumulative.append(acc)
    classes = [c for c, _ in entries]
    labels = [l for _, l in entries]
    return classes, cumulative, labels


class EndlessDeck:
    """永无止境模式 —— 无限牌库, 抽牌服从单挑牌库的构成概率。"""

    def __init__(self) -> None:
        self._classes, self._cumulative, self._labels = build_solo_probability_table()
        self._draw_count: int = 0

    def __len__(self) -> int:
        return 99999

    def draw(self) -> Optional[Card]:
        r = random.random()
        idx = 0
        for i, thr in enumerate(self._cumulative):
            if r <= thr:
                idx = i
                break
        else:
            idx = len(self._cumulative) - 1
        cls = self._classes[idx]
        self._draw_count += 1
        return cls(card_id=f"{self._labels[idx]}_{self._draw_count}")

    def build_shared_deck(self, scale: float = 1.0) -> None:
        pass

    def set_remaining(self, n: int) -> None:
        pass

    def is_infinite(self) -> bool:
        return True

    def stats(self) -> dict:
        return {
            label: f"{self._labels[i]}"
            for i in range(len(self._classes))
        }