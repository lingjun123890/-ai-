import random
from typing import List, Optional
from .card import (Card, AttackCard, ThoughtStampCard, StellarHydrogenCard,
                   SophonPlunderCard, DarkForestStrikeCard,
                   HealCard, DehydrationCard, BunkerPlanCard,
                   DropletImpactCard, StaircasePlanCard,
                   RedCoastCard, TechExplosionCard,
                   ResourceConvertCard, DimensionCleanupCard,
                   WallFacingCard, EscapismCard,
                   SuspicionChainCard, GravityWaveCard)
from .config import (BASIC_ATTACK_COUNT,
                     THOUGHT_STAMP_COUNT, STELLAR_HYDROGEN_COUNT,
                     PROTON_SOPHON_COUNT, DARK_FOREST_COUNT,
                     BASIC_HEAL_COUNT,
                     DEHYDRATION_COUNT, BUNKER_PLAN_COUNT,
                     DROPLET_IMPACT_COUNT, STAIRCASE_PLAN_COUNT,
                     RED_COAST_COUNT, TECH_EXPLOSION_COUNT,
                     RESOURCE_CONVERT_COUNT, DIMENSION_CLEANUP_COUNT,
                     WALL_FACING_COUNT, ESCAPISM_COUNT,
                     SUSPICION_CHAIN_COUNT, GRAVITY_WAVE_COUNT)


class Deck:
    def __init__(self, cards: Optional[List[Card]] = None) -> None:
        self._cards: List[Card] = list(cards) if cards else []

    def __len__(self) -> int:
        return len(self._cards)

    def shuffle(self) -> None:
        random.shuffle(self._cards)

    def draw(self) -> Optional[Card]:
        if not self._cards:
            return None
        return self._cards.pop()

    def build_shared_deck(self, scale: float = 1.0) -> None:
        def _scaled(n: int) -> int:
            return max(1, int(n * scale)) if scale < 1.0 else n

        for i in range(_scaled(BASIC_ATTACK_COUNT)):
            self._cards.append(AttackCard(card_id=f"攻击_{i}"))

        for i in range(_scaled(THOUGHT_STAMP_COUNT)):
            self._cards.append(ThoughtStampCard(card_id=f"思想钢印_{i}"))

        for i in range(_scaled(STELLAR_HYDROGEN_COUNT)):
            self._cards.append(StellarHydrogenCard(card_id=f"恒星级氢弹_{i}"))

        for i in range(_scaled(PROTON_SOPHON_COUNT)):
            self._cards.append(SophonPlunderCard(card_id=f"智子掠夺_{i}"))

        for i in range(_scaled(DARK_FOREST_COUNT)):
            self._cards.append(DarkForestStrikeCard(card_id=f"黑暗森林打击_{i}"))

        for i in range(_scaled(BASIC_HEAL_COUNT)):
            self._cards.append(HealCard(card_id=f"恢复_{i}"))

        for i in range(_scaled(DEHYDRATION_COUNT)):
            self._cards.append(DehydrationCard(card_id=f"脱水_{i}"))

        for i in range(_scaled(BUNKER_PLAN_COUNT)):
            self._cards.append(BunkerPlanCard(card_id=f"掩体计划_{i}"))

        for i in range(_scaled(DROPLET_IMPACT_COUNT)):
            self._cards.append(DropletImpactCard(card_id=f"水滴撞击_{i}"))

        for i in range(_scaled(STAIRCASE_PLAN_COUNT)):
            self._cards.append(StaircasePlanCard(card_id=f"阶梯计划_{i}"))

        for i in range(_scaled(RED_COAST_COUNT)):
            self._cards.append(RedCoastCard(card_id=f"红岸监听_{i}"))

        for i in range(_scaled(TECH_EXPLOSION_COUNT)):
            self._cards.append(TechExplosionCard(card_id=f"技术爆炸_{i}"))

        for i in range(_scaled(RESOURCE_CONVERT_COUNT)):
            self._cards.append(ResourceConvertCard(card_id=f"资源转化_{i}"))

        for i in range(_scaled(DIMENSION_CLEANUP_COUNT)):
            self._cards.append(DimensionCleanupCard(card_id=f"降维清理_{i}"))

        for i in range(_scaled(WALL_FACING_COUNT)):
            self._cards.append(WallFacingCard(card_id=f"面壁计划_{i}"))

        for i in range(_scaled(ESCAPISM_COUNT)):
            self._cards.append(EscapismCard(card_id=f"逃亡主义_{i}"))

        for i in range(_scaled(SUSPICION_CHAIN_COUNT)):
            self._cards.append(SuspicionChainCard(card_id=f"猜疑链_{i}"))

        for i in range(_scaled(GRAVITY_WAVE_COUNT)):
            self._cards.append(GravityWaveCard(card_id=f"引力波天线_{i}"))

        self.shuffle()

    def set_remaining(self, n: int) -> None:
        while len(self._cards) > n:
            self._cards.pop()