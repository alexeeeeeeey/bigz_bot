from datetime import date, datetime, timedelta

from api.booking import BookingApi
from api.schemas import Room, Slot
from core.config import config

DATE_FORMAT = "%d.%m.%Y"
TODAY_ALIASES = {"сегодня", "today"}
TOMORROW_ALIASES = {"завтра", "tomorrow"}
ROOM_ID_INVALID_TEXT = "Номер комнаты должен быть целым числом"
BOOKING_DATE_INVALID_TEXT = "Дата должна быть в формате ГГГГ-ММ-ДД, например 2026-04-01"
ROOM_NOT_FOUND_TEXT = "Комната с id {room_id} не найдена"
ROOMS_EMPTY_TEXT = "Комнаты не найдены."
SLOTS_EMPTY_TEXT = "Свободных слотов нет."
SLOT_LINE_TEXT = "{index}. {value} - {price} ₽"


class BookingServiceError(Exception):
    pass


def parse_room_id(raw_value: str) -> int:
    try:
        return int(raw_value.strip())
    except ValueError as exc:
        raise BookingServiceError(ROOM_ID_INVALID_TEXT) from exc


def parse_booking_date(raw_value: str, *, today: date | None = None) -> date:
    normalized = raw_value.strip().lower()
    current_day = today or date.today()

    if normalized in TODAY_ALIASES:
        return current_day
    if normalized in TOMORROW_ALIASES:
        return current_day + timedelta(days=1)

    try:
        return datetime.strptime(raw_value.strip(), DATE_FORMAT).date()
    except ValueError as exc:
        raise BookingServiceError(BOOKING_DATE_INVALID_TEXT) from exc


async def get_rooms() -> list[Room]:
    async with BookingApi(config.booking_base_url) as api:
        return await api.get_rooms()


async def get_room(room_id: int) -> Room:
    rooms = await get_rooms()
    for room in rooms:
        if room.id == room_id:
            return room
    raise BookingServiceError(ROOM_NOT_FOUND_TEXT.format(room_id=room_id))


async def get_slots(room_id: int, book_date: date) -> list[Slot]:
    async with BookingApi(config.booking_base_url) as api:
        return await api.get_slots(room_id, book_date)


async def create_booking(
    room_id: int,
    book_date: date,
    slots: list[Slot],
    fullname: str,
    phone: str,
    comment: str,
) -> None:
    async with BookingApi(config.booking_base_url) as api:
        await api.book(
            room_id=room_id,
            book_date=book_date,
            slots=slots,
            fullname=fullname,
            phone=phone,
            comment=comment,
        )


def format_rooms(rooms: list[Room]) -> str:
    if not rooms:
        return ROOMS_EMPTY_TEXT

    return "\n".join(f"{room.id}. {room.name}" for room in rooms)


def format_slots(slots: list[Slot]) -> str:
    if not slots:
        return SLOTS_EMPTY_TEXT

    return "\n".join(
        SLOT_LINE_TEXT.format(index=index, value=slot.value, price=slot.price)
        for index, slot in enumerate(slots, start=1)
    )
