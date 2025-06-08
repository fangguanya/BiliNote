import enum


class DownloadQuality(str, enum.Enum):
    fast = "fast"
    medium = "medium"
    slow = "slow"
    # 百度网盘专用质量选项
    original = "original"  # 原始质量（百度网盘）
