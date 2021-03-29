"""Utilities for weekly event schedule stuff."""
from typing import List, Dict
import datetime
from pytz import utc

class WeeklyEventSchedule:
  # Data form https://support.wotvffbe.com/hc/en-us/articles/360044674553-Weekly-Event-Quests
  # Aligned to an array where Monday is 0 and Sunday is 6, for use with datetime.datetime.weekday()
  double_drop_rates_by_day: List[str] = [
    'EXP Chamber, Gil Chamber, Ore Chamber, Growth Egg Chamber, Pot Chamber', # Monday
    'Alcryst Chamber (Fire/Wind), Esper Awakening Chamber (Fire/Wind)', # Tuesday
    'Alcryst Chamber (Water/Ice), Esper Awakening Chamber (Water/Ice)', # Wednesday
    'Alcryst Chamber (Earth/Dark), Esper Awakening Chamber (Earth/Dark)', # Thursday
    'Alcryst Chamber (Lightning/Light), Esper Awakening Chamber (Lightning/Light)', # Friday
    'Training Chamber (High Difficulty): Yellow/Red, Training Chamber (Brutal Difficulty): Red', # Saturday
    'No double drop rates' # Sunday
  ]

  # Short English names for days of the week, starting from Monday to align with datetime.datetime.weekday()
  short_days_of_the_week: List[str] = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

  @staticmethod
  def getTodaysDoubleDropRateEvents() -> str:
    """Return a string describing today's double-drop-rate events."""
    wotv_world_time = datetime.datetime.now(utc) - datetime.timedelta(hours=8)   # World time is always UTC-8, no daylight savings.
    return WeeklyEventSchedule.double_drop_rates_by_day[wotv_world_time.weekday()]

  @staticmethod
  def getTomorrowsDoubleDropRateEvents() -> str:
    """Return a string describing tomorrow's double-drop-rate events."""
    wotv_world_time = datetime.datetime.now(utc) - datetime.timedelta(hours=8)   # World time is always UTC-8, no daylight savings.
    return WeeklyEventSchedule.double_drop_rates_by_day[(wotv_world_time.weekday() + 1) % 7]

  @staticmethod
  def getDoubleDropRateSchedule(today_prefix_str: str = None, today_suffix_str: str = None):
    """Return a complete schedule of double drop rates, with the current day bounded by the specified optional prefix and suffix strings.
    The prefix and suffix strings can be used for, e.g., Discord formatting of the returned text.
    """
    wotv_world_day_ordinal = (datetime.datetime.now(utc) - datetime.timedelta(hours=8)).weekday()
    result = ''
    for x in range(0, 7):
      if x == wotv_world_day_ordinal and today_prefix_str:
        result += today_prefix_str
      result += WeeklyEventSchedule.short_days_of_the_week[x] + ': '
      result += WeeklyEventSchedule.double_drop_rates_by_day[x]
      if x == wotv_world_day_ordinal and today_suffix_str:
        result += today_suffix_str
      if x < 6:
        result += '\n'
    return result
