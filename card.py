from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from .config import (CARD_TEMPLATE_DESC, DEFAULT_CARD_COST, ATTACK_DAMAGE,
                     HEAL_AMOUNT,
                     DARK_FOREST_HP_THRESHOLD, STAIRCASE_HP_THRESHOLD)

if TYPE_CHECKING:
    from .engine import GameEngine


CARD_TYPES = ("攻击", "恢复", "功能", "积分")

CARD_TYPE_COLOR = {
    "攻击": "red",
    "恢复": "green",
    "功能": "purple",
    "积分": "gold",
}

CARD_TYPE_DESC = {
    "攻击": f"对敌方造成 {ATTACK_DAMAGE} 点伤害",
    "恢复": f"为己方恢复 {HEAL_AMOUNT} 点生命",
    "功能": "触发特殊效果",
    "积分": "积分上限永久 +1",
}


@dataclass
class Card:
    card_id: str
    name: str = "模板卡牌"
    description: str = CARD_TEMPLATE_DESC
    flavor: str = ""
    cost: int = DEFAULT_CARD_COST
    card_type: str = "功能"
    template_color: str = "white"

    def __post_init__(self):
        if not self.card_id:
            self.card_id = f"card_{id(self)}"
        if self.card_type in CARD_TYPE_COLOR:
            self.template_color = CARD_TYPE_COLOR[self.card_type]
        if self.description == CARD_TEMPLATE_DESC and self.card_type in CARD_TYPE_DESC:
            self.description = CARD_TYPE_DESC[self.card_type]

    def get_actual_cost(self, owner: "Player", engine: Optional["GameEngine"] = None) -> int:
        return self.cost

    def needs_target(self) -> bool:
        return False

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        pass

    def to_dict(self) -> dict:
        cls = type(self).__name__
        base = {
            "class": cls,
            "card_id": self.card_id,
            "name": self.name,
            "description": self.description,
            "cost": self.cost,
            "card_type": self.card_type,
            "template_color": self.template_color,
        }
        extras = {k: v for k, v in self.__dict__.items()
                  if k not in base and not k.startswith("_")}
        base.update(extras)
        return base

    @classmethod
    def from_dict(cls, data: dict) -> "Card":
        class_name = data.get("class", "Card")
        cls_map = {
            "Card": Card,
            "AttackCard": AttackCard,
            "ThoughtStampCard": ThoughtStampCard,
            "StellarHydrogenCard": StellarHydrogenCard,
            "SophonPlunderCard": SophonPlunderCard,
            "DarkForestStrikeCard": DarkForestStrikeCard,
            "HealCard": HealCard,
            "DehydrationCard": DehydrationCard,
            "BunkerPlanCard": BunkerPlanCard,
            "DropletImpactCard": DropletImpactCard,
            "StaircasePlanCard": StaircasePlanCard,
            "RedCoastCard": RedCoastCard,
            "TechExplosionCard": TechExplosionCard,
            "ResourceConvertCard": ResourceConvertCard,
            "DimensionCleanupCard": DimensionCleanupCard,
            "WallFacingCard": WallFacingCard,
            "EscapismCard": EscapismCard,
            "SuspicionChainCard": SuspicionChainCard,
            "GravityWaveCard": GravityWaveCard,
        }
        target_cls = cls_map.get(class_name, Card)
        kwargs = {k: v for k, v in data.items() if k != "class"}
        return target_cls(**kwargs)


@dataclass
class AttackCard(Card):
    damage: int = ATTACK_DAMAGE

    def __post_init__(self):
        self.cost = DEFAULT_CARD_COST
        self.card_type = "攻击"
        if not self.name or self.name == "模板卡牌":
            self.name = "基础打击"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = f"对敌方造成 {self.damage} 点伤害。"
        if not self.flavor:
            self.flavor = "常规物理武器或低能激光试探。"
        self.template_color = CARD_TYPE_COLOR["攻击"]

    def needs_target(self) -> bool:
        return True

    def on_play(self, owner: "Player", target: Optional["Player"] = None, engine=None) -> None:
        if target is not None:
            target.take_damage(self.damage)


@dataclass
class ThoughtStampCard(Card):
    damage: int = 3

    def __post_init__(self):
        self.cost = 0
        self.card_type = "攻击"
        if not self.name or self.name == "模板卡牌":
            self.name = "思想钢印"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = (
                f"对敌方造成 {self.damage} 点伤害。"
                f"代价: 你的积分上限永久 -1。"
            )
        if not self.flavor:
            self.flavor = "透支未来的资源, 换取当下的绝对爆发。"
        self.template_color = CARD_TYPE_COLOR["攻击"]

    def needs_target(self) -> bool:
        return True

    def on_play(self, owner: "Player", target: Optional["Player"] = None, engine=None) -> None:
        if target is not None:
            target.take_damage(self.damage)
        owner.decrease_max_score(1)


@dataclass
class StellarHydrogenCard(Card):
    damage: int = 10

    def __post_init__(self):
        self.cost = 3
        self.card_type = "攻击"
        if not self.name or self.name == "模板卡牌":
            self.name = "恒星级氢弹"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = f"对敌方造成 {self.damage} 点伤害。"
        if not self.flavor:
            self.flavor = "面壁者雷迪亚兹的终极计划, 以毁灭太阳系为代价的绝对威慑。"
        self.template_color = CARD_TYPE_COLOR["攻击"]

    def needs_target(self) -> bool:
        return True

    def on_play(self, owner: "Player", target: Optional["Player"] = None, engine=None) -> None:
        if target is not None:
            target.take_damage(self.damage)


@dataclass
class SophonPlunderCard(Card):
    damage: int = 2
    heal_amount: int = 2

    def __post_init__(self):
        self.cost = 2
        self.card_type = "攻击"
        if not self.name or self.name == "模板卡牌":
            self.name = "智子掠夺"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = f"对敌方造成 {self.damage} 点伤害, 并恢复自身 {self.heal_amount} 点生命。"
        if not self.flavor:
            self.flavor = "利用智子干扰敌方实验, 将对方的科技与资源转化为己用。"
        self.template_color = CARD_TYPE_COLOR["攻击"]

    def needs_target(self) -> bool:
        return True

    def on_play(self, owner: "Player", target: Optional["Player"] = None, engine=None) -> None:
        if target is not None:
            target.take_damage(self.damage)
        owner.heal(self.heal_amount)


@dataclass
class DarkForestStrikeCard(Card):
    damage: int = 2

    def __post_init__(self):
        self.cost = 1
        self.card_type = "攻击"
        if not self.name or self.name == "模板卡牌":
            self.name = "黑暗森林打击"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = (
                f"对敌方造成 {self.damage} 点伤害; "
                f"若敌方生命值低于 {DARK_FOREST_HP_THRESHOLD} 点, 则伤害翻倍 ({self.damage * 2} 点伤害)。"
            )
        if not self.flavor:
            self.flavor = "一旦暴露坐标且处于弱势, 高级文明将毫不犹豫地将其抹除。"
        self.template_color = CARD_TYPE_COLOR["攻击"]

    def needs_target(self) -> bool:
        return True

    def on_play(self, owner: "Player", target: Optional["Player"] = None, engine=None) -> None:
        if target is None:
            return
        dmg = self.damage
        if target.health < DARK_FOREST_HP_THRESHOLD:
            dmg *= 2
        target.take_damage(dmg)


@dataclass
class HealCard(Card):
    heal_amount: int = HEAL_AMOUNT

    def __post_init__(self):
        self.cost = 2
        self.card_type = "恢复"
        if not self.name or self.name == "模板卡牌":
            self.name = "生态恢复"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = f"恢复自身 {self.heal_amount} 点生命值。"
        if not self.flavor:
            self.flavor = "乱纪元结束后的文明重建与自我修复。"
        self.template_color = CARD_TYPE_COLOR["恢复"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None, engine=None) -> None:
        owner.heal(self.heal_amount)


@dataclass
class DehydrationCard(Card):
    heal_amount: int = 2

    def __post_init__(self):
        self.cost = 0
        self.card_type = "恢复"
        if not self.name or self.name == "模板卡牌":
            self.name = "脱水"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = f"恢复自身 {self.heal_amount} 点生命值。"
        if not self.flavor:
            self.flavor = "三体人在乱纪元来临时的保命本能, 不消耗额外资源。"
        self.template_color = CARD_TYPE_COLOR["恢复"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        owner.heal(self.heal_amount)


@dataclass
class BunkerPlanCard(Card):
    heal_amount: int = 12

    def __post_init__(self):
        self.cost = 4
        self.card_type = "恢复"
        if not self.name or self.name == "模板卡牌":
            self.name = "掩体计划"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = f"恢复自身 {self.heal_amount} 点生命值。"
        if not self.flavor:
            self.flavor = "消耗巨量资源建造掩体, 在黑暗森林打击下争取一线生机。"
        self.template_color = CARD_TYPE_COLOR["恢复"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        owner.heal(self.heal_amount)


@dataclass
class DropletImpactCard(Card):
    damage: int = 2
    heal_amount: int = 2

    def __post_init__(self):
        self.cost = 2
        self.card_type = "恢复"
        if not self.name or self.name == "模板卡牌":
            self.name = "水滴撞击"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = f"对敌方造成 {self.damage} 点伤害, 并恢复自身 {self.heal_amount} 点生命。"
        if not self.flavor:
            self.flavor = "强互作用力探测器\"水滴\"的绝对穿透, 以战养战, 攻防一体。"
        self.template_color = CARD_TYPE_COLOR["恢复"]

    def needs_target(self) -> bool:
        return True

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        if target is not None:
            target.take_damage(self.damage)
        owner.heal(self.heal_amount)


@dataclass
class StaircasePlanCard(Card):
    heal_amount: int = 4

    def __post_init__(self):
        self.cost = 2
        self.card_type = "恢复"
        if not self.name or self.name == "模板卡牌":
            self.name = "阶梯计划"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = (
                f"恢复自身 {self.heal_amount} 点生命值。"
                f"若自身生命值低于 20 点, 额外抽 1 张牌。"
            )
        if not self.flavor:
            self.flavor = "云天明的大脑送入太空, 在绝境中为人类传递了拯救文明的希望。"
        self.template_color = CARD_TYPE_COLOR["恢复"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        draw_on_low_hp = owner.health < STAIRCASE_HP_THRESHOLD
        owner.heal(self.heal_amount)
        if draw_on_low_hp and engine is not None:
            card = engine.shared_deck.draw()
            if card is not None:
                owner.add_card(card)


@dataclass
class RedCoastCard(Card):
    draw_count: int = 1

    def __post_init__(self):
        self.cost = 1
        self.card_type = "功能"
        if not self.name or self.name == "模板卡牌":
            self.name = "红岸监听"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = f"消耗 {self.cost} 积分, 抽 {self.draw_count} 张牌。"
        if not self.flavor:
            self.flavor = "向宇宙发送信号, 探寻未知的希望与危机。"
        self.template_color = CARD_TYPE_COLOR["功能"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        if engine is None:
            return
        for _ in range(self.draw_count):
            card = engine.shared_deck.draw()
            if card is None:
                break
            owner.add_card(card)


@dataclass
class TechExplosionCard(Card):
    bonus_amount: int = 1

    def __post_init__(self):
        self.cost = 1
        self.card_type = "功能"
        if not self.name or self.name == "模板卡牌":
            self.name = "技术爆炸"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = f"消耗 {self.cost} 积分, 本回合你打出的所有攻击牌伤害 +{self.bonus_amount}。"
        if not self.flavor:
            self.flavor = "低级文明在短期内实现科技的飞跃。"
        self.template_color = CARD_TYPE_COLOR["功能"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        owner.attack_bonus += self.bonus_amount


@dataclass
class ResourceConvertCard(Card):
    draw_count: int = 2
    discard_count: int = 1

    def __post_init__(self):
        self.cost = 2
        self.card_type = "功能"
        if not self.name or self.name == "模板卡牌":
            self.name = "资源转化"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = (
                f"消耗 {self.cost} 积分, 弃掉 {self.discard_count} 张手牌, 然后抽 {self.draw_count} 张牌。"
            )
        if not self.flavor:
            self.flavor = "将废弃的科研资料重新解析, 寻找新的突破口。"
        self.template_color = CARD_TYPE_COLOR["功能"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        if engine is None:
            return
        for _ in range(self.discard_count):
            if owner.hand:
                removed = owner.hand.pop()
                owner.discard.append(removed)
        for _ in range(self.draw_count):
            card = engine.shared_deck.draw()
            if card is None:
                break
            owner.add_card(card)


@dataclass
class DimensionCleanupCard(Card):
    damage: int = 4

    def __post_init__(self):
        self.cost = 3
        self.card_type = "功能"
        if not self.name or self.name == "模板卡牌":
            self.name = "降维清理"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = (
                f"消耗 {self.cost} 积分, 对敌方造成 {self.damage} 点伤害。"
                f"若本回合已打出过【技术爆炸】, 则此牌消耗变为 0。"
            )
        if not self.flavor:
            self.flavor = "二向箔打击, 通过科技联动实现毁灭性的降维清理。"
        self.template_color = CARD_TYPE_COLOR["功能"]

    def needs_target(self) -> bool:
        return True

    def get_actual_cost(self, owner: "Player", engine: Optional["GameEngine"] = None) -> int:
        if engine is not None:
            for c in engine._turn_played_cards:
                if type(c).__name__ == "TechExplosionCard":
                    return 0
        return self.cost

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        if target is not None:
            target.take_damage(self.damage)
        if owner.attack_bonus > 0 and target is not None and target.is_alive():
            target.take_damage(owner.attack_bonus)


@dataclass
class WallFacingCard(Card):
    bonus: int = 1

    def __post_init__(self):
        self.cost = 3
        self.card_type = "积分"
        if not self.name or self.name == "模板卡牌":
            self.name = "面壁计划"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = (
                f"消耗 {self.cost} 积分, 积分上限永久 +{self.bonus}。"
                f"本回合跳过抽牌。"
            )
        if not self.flavor:
            self.flavor = "将全部资源投入秘密战略, 忍受长期的孤独, 只为未来的终极一击。"
        self.template_color = CARD_TYPE_COLOR["积分"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        owner.increase_max_score(self.bonus)
        owner.skip_next_draw = True


@dataclass
class EscapismCard(Card):
    bonus: int = 1
    self_damage: int = 3

    def __post_init__(self):
        self.cost = 3
        self.card_type = "积分"
        if not self.name or self.name == "模板卡牌":
            self.name = "逃亡主义"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = (
                f"消耗 {self.cost} 积分, 积分上限永久 +{self.bonus}。"
                f"自身扣除 {self.self_damage} 点生命值。"
            )
        if not self.flavor:
            self.flavor = "为了文明的延续, 不惜牺牲一部分人, 换取未来的生存空间。"
        self.template_color = CARD_TYPE_COLOR["积分"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        owner.increase_max_score(self.bonus)
        owner.take_damage(self.self_damage)


@dataclass
class SuspicionChainCard(Card):
    bonus: int = 1
    opponent_penalty: int = 1

    def __post_init__(self):
        self.cost = 3
        self.card_type = "积分"
        if not self.name or self.name == "模板卡牌":
            self.name = "猜疑链"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = (
                f"消耗 {self.cost} 积分, 积分上限永久 +{self.bonus}。"
                f"指定对手的积分上限永久 -{self.opponent_penalty}。"
            )
        if not self.flavor:
            self.flavor = "无法判断对方是善意还是恶意, 为了自保只能先发制人, 掠夺对方的生存资源。"
        self.template_color = CARD_TYPE_COLOR["积分"]

    def needs_target(self) -> bool:
        return True

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        owner.increase_max_score(self.bonus)
        if target is not None and target is not owner:
            target.decrease_max_score(self.opponent_penalty)


@dataclass
class GravityWaveCard(Card):
    bonus: int = 1
    score_gain: int = 3

    def __post_init__(self):
        self.cost = 3
        self.card_type = "积分"
        if not self.name or self.name == "模板卡牌":
            self.name = "引力波天线"
        if not self.description or self.description == CARD_TEMPLATE_DESC:
            self.description = (
                f"消耗 {self.cost} 积分, 积分上限永久 +{self.bonus}。"
                f"获得 {self.score_gain} 积分。"
            )
        if not self.flavor:
            self.flavor = "罗辑建立的威慑系统, 只要天线还在, 就能持续为人类提供战略资源与和平。"
        self.template_color = CARD_TYPE_COLOR["积分"]

    def on_play(self, owner: "Player", target: Optional["Player"] = None,
                engine: Optional["GameEngine"] = None) -> None:
        owner.increase_max_score(self.bonus)
        owner.score = min(owner.max_score, owner.score + self.score_gain)