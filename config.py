HAND_TARGET = 5                  # 初始/每回合抽牌数
STARTING_HEALTH = 40             # 起始生命值

STARTING_SCORE = 1               # 起始科技等级
STARTING_MAX_SCORE = 1           # 起始科技等级上限
MAX_SCORE_CAP = 11               # 科技等级上限封顶

DEFAULT_CARD_COST = 1            # 卡牌默认消耗
ATTACK_DAMAGE = 2                # 基础攻击伤害
HEAL_AMOUNT = 4                  # 基础治疗量
SCORE_BONUS_COST = 2             # 科技奖励类卡牌消耗

BASIC_ATTACK_COUNT = 60          # 基础攻击牌数量
THOUGHT_STAMP_COUNT = 6          # 思维印章牌数量
STELLAR_HYDROGEN_COUNT = 4       # 恒星氢牌数量
PROTON_SOPHON_COUNT = 4          # 质子寄希思牌数量
DARK_FOREST_COUNT = 2            # 黑暗森林牌数量
BASIC_HEAL_COUNT = 30            # 基础治疗牌数量
DEHYDRATION_COUNT = 4            # 脱水牌数量
BUNKER_PLAN_COUNT = 4            # 掩体计划牌数量
DROPLET_IMPACT_COUNT = 4         # 水滴冲击牌数量
STAIRCASE_PLAN_COUNT = 2         # 阶梯计划牌数量
SPECIAL_HEAL_COUNT = DEHYDRATION_COUNT + BUNKER_PLAN_COUNT + DROPLET_IMPACT_COUNT + STAIRCASE_PLAN_COUNT  # 特殊治疗牌总数
RED_COAST_COUNT = 30             # 红岸牌数量
TECH_EXPLOSION_COUNT = 30        # 技术爆炸牌数量
RESOURCE_CONVERT_COUNT = 20      # 资源转换牌数量
DIMENSION_CLEANUP_COUNT = 16     # 维度清理牌数量
FUNCTION_COUNT = RED_COAST_COUNT + TECH_EXPLOSION_COUNT + RESOURCE_CONVERT_COUNT + DIMENSION_CLEANUP_COUNT  # 功能牌总数
WALL_FACING_COUNT = 6            # 面壁牌数量
ESCAPISM_COUNT = 6               # 逃避主义牌数量
SUSPICION_CHAIN_COUNT = 4        # 猜疑链牌数量
GRAVITY_WAVE_COUNT = 4           # 引力波牌数量
SCORE_BONUS_COUNT = WALL_FACING_COUNT + ESCAPISM_COUNT + SUSPICION_CHAIN_COUNT + GRAVITY_WAVE_COUNT  # 科技奖励牌总数
SPECIAL_ATTACK_COUNT = THOUGHT_STAMP_COUNT + STELLAR_HYDROGEN_COUNT + PROTON_SOPHON_COUNT + DARK_FOREST_COUNT  # 特殊攻击牌总数
DECK_TOTAL_SIZE = (BASIC_ATTACK_COUNT + SPECIAL_ATTACK_COUNT
                   + BASIC_HEAL_COUNT + SPECIAL_HEAL_COUNT
                   + FUNCTION_COUNT + SCORE_BONUS_COUNT)  # 牌库总张数

DARK_FOREST_HP_THRESHOLD = 20    # 黑暗森林触发血量阈值
STAIRCASE_HP_THRESHOLD = 20      # 阶梯计划触发血量阈值

TRAINING_OPPONENT_HP = 10000     # 训练模式对手血量
TRAINING_OPPONENT_MAX_SCORE = 0  # 训练模式对手科技上限

CARD_TEMPLATE_DESC = "占位卡牌，待后续完善"  # 卡牌模板描述