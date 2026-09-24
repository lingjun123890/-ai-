# 黑暗森林 · 三体回合制卡牌

一款以《三体》科幻宇宙为背景的 **Python + Pygame** 回合制卡牌对战游戏。

> 给岁月以文明，而不是给文明以岁月。

---

## 游戏特色

- 🌌 **三体主题卡牌** — 黑暗森林打击、思想钢印、面壁计划、引力波天线……全部源自原著设定
- 🎮 **多种对战模式** — 离线本地双人、训练模式（模拟目标）、1v1、2v2、四人混战
- 🌐 **局域网联机** — 直连或中继服务器穿透 NAT
- 🃏 **四大类 18 张卡牌** — 攻击、恢复、功能、积分，可叠加连锁效果
- 🧠 **科技积分系统** — 每回合积分上限递增（封顶 11），决定出牌节奏
- 🖥️ **纯 Pygame 自研 GUI** — 无外部前端依赖

## 目录结构

所有开源代码均在 `` 目录内：

```
game/
├── __main__.py          # 支持 `python -m game` 启动
├── main.py              # 入口：模式选择与路由
├── engine.py            # 游戏引擎：回合流转、出牌校验、胜负判定
├── player.py            # 玩家数据类
├── card.py              # 全部 18 张卡牌的类定义
├── deck.py              # 共享牌库构建与抽牌
├── config.py            # 游戏常量与数值配置（改这里调平衡）
├── gui.py               # Pygame 界面与事件循环（主菜单、大厅、对战）
├── renderer.py          # 渲染抽象层（ABC）
├── network.py           # TCP 联机层：直连 / 多人广播 / Ping 测延迟
├── relay.py             # 独立中继服务器（绕过 NAT）
├── music.py             # 背景音乐管理（支持本地文件夹扫描）
└── credits/
    └── credits_data.py  # 鸣谢名单
```

## 环境要求

- Python ≥ 3.12
- pygame ≥ 2.5.0

## 快速开始

```bash
pip install pygame
python -m game
```
或使用打包好的压缩包进行游玩

### 联机对战

**方式一：主机直连**

1. 主菜单选择「创建房间」，记下显示的 `IP:端口`
2. 对手选择「加入房间」，输入该地址
3. 跨公网需自行做 NAT 穿透（frp / zerotier / tailscale）

**方式二：中继服务器（推荐公网对战）**

在任意一台有公网 IP 的机器上：

```bash
python -m game.relay --host 0.0.0.0 --port 9998
```

双方填入同一个中继地址和同一个房间号即可互通。

## 游戏规则速览

### 基础数值

| 属性 | 初始值 |
| --- | --- |
| 生命值 | 40 |
| 科技积分 | 1（每回合自动补满至上限） |
| 科技上限 | 1（每回合 +1，封顶 11） |
| 手牌 | 5（每回合自动抽满） |
| 胜利条件 | 对手生命值降至 0 |

### 四大卡牌类型

| 类型 | 颜色 | 核心效果 | 代表卡牌 |
| --- | --- | --- | --- |
| 攻击 | 红 | 对敌方造成伤害 | 基础打击、恒星级氢弹、黑暗森林打击、智子掠夺 |
| 恢复 | 绿 | 回复生命 / 攻防一体 | 生态恢复、掩体计划、水滴撞击、阶梯计划 |
| 功能 | 紫 | 抽牌 / 增益 / 联动 | 红岸监听、技术爆炸、资源转化、降维清理 |
| 积分 | 金 | 永久提升科技上限（有代价） | 面壁计划、逃亡主义、猜疑链、引力波天线 |

### 关键机制

- **黑暗森林打击**：对方血量 < 20 时伤害翻倍
- **降维清理联动**：本回合先打出「技术爆炸」，消耗变为 0（免费 4 伤害）
- **猜疑链**：唯一能降低对手科技上限的卡，克制后期流
- **训练模式**：对手 10000 血、锁死科技，适合练手

## 扩展：添加新卡牌

在 `card.py` 里继承 `Card`，实现 `on_play()`：

```python
from dataclasses import dataclass
from game.card import Card

@dataclass
class MyNewCard(Card):
    def __post_init__(self):
        self.name = "我的新卡"
        self.cost = 2
        self.card_type = "功能"
        self.description = "自定义效果说明"

    def needs_target(self) -> bool:
        return False   # True 表示需要选敌方目标

    def on_play(self, owner, target=None, engine=None):
        # 写效果逻辑
        pass
```

然后在同文件的 `Card.from_dict()` 里，把类名加到 `cls_map` 字典即可支持联机序列化：

```python
cls_map = {
    # ...已有卡牌...
    "MyNewCard": MyNewCard,
}
```

最后在 `deck.py` 的 `build_shared_deck()` 里按数量添加进牌库。

## 数值调整

所有游戏常量集中在 `config.py`，直接修改即可，无需改引擎代码：

```python
HAND_TARGET = 5             # 每回合抽牌数
STARTING_HEALTH = 40        # 起始生命值
MAX_SCORE_CAP = 11          # 科技上限封顶
BASIC_ATTACK_COUNT = 60     # 基础打击在牌库中的数量
# ...每张卡都有对应的数量常量
```

## 架构说明

```
┌─────────────┐    调用    ┌─────────────┐    持有    ┌─────────────┐
│  gui.py     │ ────────▶  │ engine.py   │ ────────▶  │  card.py    │
│ (pygame)    │            │ (GameEngine)│            │  (Card 子类)│
└─────────────┘            └──────┬──────┘            └─────────────┘
                                   │
                          ┌────────▼────────┐
                          │   player.py     │
                          │   deck.py       │
                          │   config.py     │
                          └─────────────────┘

        联机：gui.py 持有 network.py，
             通过 engine.snapshot() / apply_remote_state() 同步状态
```

- `engine.py` 只持有 `BaseRenderer` 抽象，不依赖 Pygame — 可以脱离 GUI 做纯逻辑测试
- `network.py` 独立封装，基于 TCP Socket + pickle 序列化，带 Ping 心跳
- `relay.py` 是可独立运行的中继服务器，双线程管道转发，不依赖游戏代码

## 许可证

MIT License

---

> 宇宙就是一座黑暗森林，每个文明都是带枪的猎人……
