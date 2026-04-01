from datetime import datetime


def get_time() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"当前时间是 {now}"


def get_weather_mock(city: str) -> str:
    city_name = (city or "本地").strip() or "本地"
    return f"{city_name}今天天气晴，气温 22 到 28 度。"
