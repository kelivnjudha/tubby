from __future__ import annotations


def format_duration(seconds: int | float | None) -> str:
    """Format a duration in seconds as M:SS or H:MM:SS."""
    if seconds is None:
        return "Unknown"

    try:
        total_seconds = max(0, int(seconds))
    except (TypeError, ValueError, OverflowError):
        return "Unknown"

    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_eta(seconds: int | float | None) -> str:
    if seconds is None:
        return "Unknown"
    return format_duration(seconds)


def format_count(value: int | float | None) -> str:
    if value is None:
        return "Unknown"

    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return "Unknown"

    return f"{number:,}"


def format_bytes(value: int | float | None) -> str:
    if value is None:
        return "Unknown"

    try:
        size = float(value)
    except (TypeError, ValueError, OverflowError):
        return "Unknown"

    if size < 0:
        return "Unknown"

    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def format_download_status(
    downloaded_bytes: int | float | None,
    total_bytes: int | float | None,
    speed_bytes: int | float | None = None,
    eta_seconds: int | float | None = None,
) -> tuple[float, str]:
    downloaded = _optional_float(downloaded_bytes) or 0
    total = _optional_float(total_bytes)
    speed = _optional_float(speed_bytes)
    eta = _optional_float(eta_seconds)

    if total and total > 0:
        ratio = min(1.0, max(0.0, downloaded / total))
        text = (
            f"{ratio * 100:4.1f}% - {format_bytes(downloaded)} downloaded "
            f"of {format_bytes(total)} file size"
        )
    else:
        ratio = 0.0
        text = f"{format_bytes(downloaded)} downloaded"

    details: list[str] = []
    if speed:
        details.append(f"{format_bytes(speed)}/s")
    if eta is not None:
        details.append(f"{format_eta(eta)} left")

    if details:
        text = f"{text} ({', '.join(details)})"

    return ratio, text


def _optional_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None
