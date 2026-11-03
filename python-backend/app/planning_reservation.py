"""Share the weekly reservation between rule planners and AI preparation."""

def reservation_key(cycle_start) -> str:
    return f"live:{cycle_start:%Y%m%d}"


def ai_preparation_exists(cursor, cycle_start) -> bool:
    cursor.execute(
        "SELECT id FROM godp_ai_preparation WHERE reservation_key=%s AND del_flag='N' LIMIT 1",
        (reservation_key(cycle_start),),
    )
    return cursor.fetchone() is not None
