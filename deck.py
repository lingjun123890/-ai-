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

    def add_card(self, card: Card) -> None:
        self._cards.append(card)

    def add_cards(self, cards: List[Card]) -> None:
        self._cards.extend(cards)

    def append_solo_standard(self) -> None:
        def _scaled(n: int) -> int:
            return max(1, int(n * 0.5)) if 0.5 < 1.0 else n

        existing_ids = {c.card_id for c in self._cards}
        new_cards: List[Card] = []

        def _make(card_cls, raw_count, prefix):
            for i in range(_scaled(raw_count)):
                cid = f"death_refill_{prefix}_{i}"
                if cid in existing_ids:
                    for j in range(10000):
                        cid = f"death_refill_{prefix}_{i}_{j}"
                        if cid not in existing_ids:
                            break
                new_cards.append(card_cls(card_id=cid))
                existing_ids.add(cid)

        _make(AttackCard, BASIC_ATTACK_COUNT, "攻击")
        _make(ThoughtStampCard, THOUGHT_STAMP_COUNT, "思想钢印")
        _make(StellarHydrogenCard, STELLAR_HYDROGEN_COUNT, "恒星级氢弹")
        _make(SophonPlunderCard, PROTON_SOPHON_COUNT, "智子掠夺")
        _make(DarkForestStrikeCard, DARK_FOREST_COUNT, "黑暗森林打击")
        _make(HealCard, BASIC_HEAL_COUNT, "恢复")
        _make(DehydrationCard, DEHYDRATION_COUNT, "脱水")
        _make(BunkerPlanCard, BUNKER_PLAN_COUNT, "掩体计划")
        _make(DropletImpactCard, DROPLET_IMPACT_COUNT, "水滴撞击")
        _make(StaircasePlanCard, STAIRCASE_PLAN_COUNT, "阶梯计划")
        _make(RedCoastCard, RED_COAST_COUNT, "红岸监听")
        _make(TechExplosionCard, TECH_EXPLOSION_COUNT, "技术爆炸")
        _make(ResourceConvertCard, RESOURCE_CONVERT_COUNT, "资源转化")
        _make(DimensionCleanupCard, DIMENSION_CLEANUP_COUNT, "降维清理")
        _make(WallFacingCard, WALL_FACING_COUNT, "面壁计划")
        _make(EscapismCard, ESCAPISM_COUNT, "逃亡主义")
        _make(SuspicionChainCard, SUSPICION_CHAIN_COUNT, "猜疑链")
        _make(GravityWaveCard, GRAVITY_WAVE_COUNT, "引力波天线")
        _make(DeterrenceEraCard, DETERRENCE_ERA_COUNT, "威慑纪元")

        self._cards.extend(new_cards)
        self.shuffle()

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

        for i in range(_scaled(DETERRENCE_ERA_COUNT)):
            self._cards.append(DeterrenceEraCard(card_id=f"威慑纪元_{i}"))

        self.shuffle()

    def set_remaining(self, n: int) -> None:
        while len(self._cards) > n:
            self._cards.pop()