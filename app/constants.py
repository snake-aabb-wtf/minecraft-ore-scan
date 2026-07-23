ALL_ORES = [
    ("minecraft:diamond_ore", "钻石"),
    ("minecraft:deepslate_diamond_ore", "深板岩钻石"),
    ("minecraft:ancient_debris", "远古残骸"),
    ("minecraft:iron_ore", "铁矿"),
    ("minecraft:deepslate_iron_ore", "深层铁矿"),
    ("minecraft:gold_ore", "金矿"),
    ("minecraft:deepslate_gold_ore", "深层金矿"),
    ("minecraft:coal_ore", "煤矿"),
    ("minecraft:deepslate_coal_ore", "深层煤矿"),
    ("minecraft:copper_ore", "铜矿"),
    ("minecraft:deepslate_copper_ore", "深层铜矿"),
    ("minecraft:redstone_ore", "红石矿"),
    ("minecraft:deepslate_redstone_ore", "深层红石矿"),
    ("minecraft:lapis_ore", "青金石矿"),
    ("minecraft:deepslate_lapis_ore", "深层青金石矿"),
    ("minecraft:emerald_ore", "绿宝石矿"),
    ("minecraft:deepslate_emerald_ore", "深层绿宝石矿"),
    ("minecraft:nether_quartz_ore", "下界石英矿"),
    ("minecraft:nether_gold_ore", "下界金矿"),
]

OVERWORLD_ORES = [
    ("minecraft:diamond_ore", "钻石"),
    ("minecraft:deepslate_diamond_ore", "深板岩钻石"),
    ("minecraft:iron_ore", "铁矿"),
    ("minecraft:deepslate_iron_ore", "深层铁矿"),
    ("minecraft:gold_ore", "金矿"),
    ("minecraft:deepslate_gold_ore", "深层金矿"),
    ("minecraft:coal_ore", "煤矿"),
    ("minecraft:deepslate_coal_ore", "深层煤矿"),
    ("minecraft:copper_ore", "铜矿"),
    ("minecraft:deepslate_copper_ore", "深层铜矿"),
    ("minecraft:redstone_ore", "红石矿"),
    ("minecraft:deepslate_redstone_ore", "深层红石矿"),
    ("minecraft:lapis_ore", "青金石矿"),
    ("minecraft:deepslate_lapis_ore", "深层青金石矿"),
    ("minecraft:emerald_ore", "绿宝石矿"),
    ("minecraft:deepslate_emerald_ore", "深层绿宝石矿"),
]

NETHER_ORES = [
    ("minecraft:ancient_debris", "远古残骸"),
    ("minecraft:nether_quartz_ore", "下界石英矿"),
    ("minecraft:nether_gold_ore", "下界金矿"),
]

END_ORES = []

DIMENSION_ORES = {
    "minecraft:overworld": OVERWORLD_ORES,
    "minecraft:the_nether": NETHER_ORES,
    "minecraft:the_end": END_ORES,
}

DIMENSION_DEFAULT_ORES = {
    "minecraft:overworld": {"minecraft:diamond_ore", "minecraft:deepslate_diamond_ore"},
    "minecraft:the_nether": {"minecraft:ancient_debris", "minecraft:nether_quartz_ore", "minecraft:nether_gold_ore"},
    "minecraft:the_end": set(),
}

ORE_OPTIONS = ALL_ORES

DIMENSIONS = [
    ("minecraft:overworld", "主世界"),
    ("minecraft:the_nether", "下界"),
    ("minecraft:the_end", "末地"),
]

VERSION_TYPE_OPTIONS = [
    ("release", "Release 正式版"),
    ("snapshot", "Snapshot 快照版"),
]

MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
ADOPTIUM_RELEASES_URL = "https://adoptium.net/zh-CN/temurin/releases"

RCON_PASSWORD = "ore_scan_local"
RCON_PORT = 25575
