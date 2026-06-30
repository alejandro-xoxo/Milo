import random

def get_current_weather(location: str) -> str:
    """
    Get the current weather forecast for a given location.
    
    Args:
        location: The city and state/country, e.g., "San Francisco, CA" or "Madrid, Spain".
        
    Returns:
        A string describing the weather forecast.
    """
    conditions = ["Sunny", "Partly Cloudy", "Rainy", "Cloudy", "Windy", "Stormy"]
    temp = random.randint(12, 32)
    humidity = random.randint(40, 90)
    return f"Weather forecast for {location}: {random.choice(conditions)}, Temperature: {temp}°C, Humidity: {humidity}%."
