"""Calendar and date utilities."""
import pandas as pd
from typing import Tuple


def make_calendar(start_date: str, n_months: int) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Return (monthly_dates, quarterly_dates) period-end timestamps."""
    months = pd.date_range(start_date, periods=n_months, freq="ME")
    quarters = months[months.month.isin([3, 6, 9, 12])]
    return months, quarters
