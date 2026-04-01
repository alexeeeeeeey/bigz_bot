import re
from datetime import date, timedelta
from enum import StrEnum

from aiomax import Callback, CommandContext, Message, Router, buttons
from aiomax.filters import startswith, state
from aiomax.fsm import FSMCursor

from api.schemas import Slot
from services.booking import (
    BookingServiceError,
    create_booking,
    format_rooms,
    format_slots,
    get_room,
    get_rooms,
    get_slots,
    parse_booking_date,
    parse_room_id,
)

router = Router()

BOOKING_ROOM_CALLBACK_PREFIX = "booking:room:"
BOOKING_DATE_CALLBACK_PREFIX = "booking:date:"
BOOKING_CONFIRM_SUBMIT_CALLBACK = "booking:confirm:submit"
BOOKING_CONFIRM_CANCEL_CALLBACK = "booking:confirm:cancel"
PHONE_ONLY_ROOM_ID = 2
PHONE_ONLY_BOOKING_TEXT = (
    "Для этой комнаты запись только по телефону:\n`8-8142-(63-53-93)`"
)

ROOMS_LOAD_ERROR_TEXT = "Не удалось загрузить комнаты: {error}"
BOOKING_START_ERROR_TEXT = "Не удалось начать бронирование: {error}"
ROOM_SELECT_ERROR_TEXT = "Не удалось выбрать комнату: {error}"
DATE_CHANGE_ERROR_TEXT = "Не удалось сменить дату: {error}"
SLOTS_REFRESH_ERROR_TEXT = "Не удалось загрузить слоты: {error}"
ROOMS_LIST_TEXT = "Доступные комнаты:\n\n{rooms}"
BOOKING_PICK_ROOM_TEXT = (
    "Выбери комнату кнопкой или отправь её номер сообщением.\n\n{rooms}"
)
BOOKING_DATE_PICK_TEXT = (
    "Комната: {room_name}\n\n"
    "Выбери дату кнопкой ниже или отправь её в формате ДД.ММ.ГГГГ"
)
ACTIVE_DIALOG_MISSING_TEXT = "Активного диалога нет."
DIALOG_RESET_TEXT = "Диалог бронирования сброшен."
NO_SLOTS_TEXT = "Свободных слотов нет."
SLOTS_HEADER_TEXT = "Свободные слоты:"
BOOKING_EMPTY_DATE_TEXT = (
    "На этой дате свободных слотов нет.\n"
    "Листай даты кнопками ниже или отправь другую дату сообщением."
)
BOOKING_SLOT_PROMPT_TEXT = (
    "Отправь номера слотов.\n"
    "Подойдёт любой разделитель: пробел, запятая, точка, слэш, дефис."
)
BOOKING_STATE_LOST_TEXT = "Состояние диалога потеряно. Запусти `/book` ещё раз."
BOOKING_EMPTY_SLOTS_DATE_TEXT = (
    "На выбранной дате нет слотов.\n"
    "Выбери другую дату кнопками ниже или отправь её сообщением."
)
BOOKING_NAME_TEXT = "Отправь имя и фамилию для брони."
BOOKING_NAME_SHORT_TEXT = "Имя слишком короткое. Отправь имя и фамилию целиком."
BOOKING_PHONE_TEXT = "Отправь номер телефона для связи."
BOOKING_PHONE_INVALID_TEXT = "Похоже на неверный номер. Пример: `+7 999 123-45-67`"
BOOKING_COMMENT_TEXT = (
    "Отправь комментарий для брони\nили нажми кнопку `Нет комментария`."
)
NO_COMMENT_BUTTON_TEXT = "Нет комментария"
BOOKING_CONFIRM_TEXT = (
    "Проверь заявку:\n\n"
    "Комната: {room_name}\n"
    "Дата: {book_date}\n"
    "Слоты:\n{slot_lines}\n"
    "Итого: {total_price} ₽\n"
    "Имя: {fullname}\n"
    "Телефон: {phone}\n"
    "Комментарий: {comment}\n\n"
    "Подтвердить отправку?"
)
BOOKING_CONFIRM_BUTTON_TEXT = "Подтвердить"
BOOKING_CONFIRM_CANCEL_BUTTON_TEXT = "Отмена"
BOOKING_CONFIRM_CANCELLED_TEXT = "Заявка отменена."
BOOKING_CONFIRM_STATE_TEXT = "Нет заявки для подтверждения."
BOOKING_FAILED_TEXT = (
    "Не удалось оформить бронь.\nПричина: {error}\n\nПопробуй ещё раз через `/book`."
)
BOOKING_SUCCESS_TEXT = (
    "Бронь отправлена.\n\n"
    "Комната: {room_name}\n"
    "Дата: {book_date}\n"
    "Слоты:\n{slot_lines}\n"
    "Итого: {total_price} ₽\n"
    "Имя: {fullname}\n"
    "Телефон: {phone}\n"
    "Комментарий: {comment}"
)
ROOM_LABEL_TEXT = "Комната: {room_name}"
DATE_LABEL_TEXT = "Дата: {date_label}"
TODAY_BUTTON_TEXT = "Сегодня {date_label}"
TOMORROW_BUTTON_TEXT = "Завтра {date_label}"
PREVIOUS_DATE_BUTTON_TEXT = "← {date_label}"
NEXT_DATE_BUTTON_TEXT = "{date_label} →"
COMMENT_SKIP_VALUES = {"", "-", "нет", "no"}
PHONE_PATTERN = re.compile(r"^\+?[\d\s()\-]{7,}$")


class BookingState(StrEnum):
    WAITING_ROOM = "booking_waiting_room"
    WAITING_DATE = "booking_waiting_date"
    WAITING_SLOT = "booking_waiting_slot"
    WAITING_NAME = "booking_waiting_name"
    WAITING_PHONE = "booking_waiting_phone"
    WAITING_COMMENT = "booking_waiting_comment"
    WAITING_CONFIRM = "booking_waiting_confirm"


@router.on_command("rooms")
async def rooms_handler(context: CommandContext):
    try:
        rooms = await get_rooms()
    except Exception as exc:
        await context.reply(ROOMS_LOAD_ERROR_TEXT.format(error=exc))
        return

    await context.reply(ROOMS_LIST_TEXT.format(rooms=format_rooms(rooms)))


@router.on_command("cancel")
async def cancel_handler(context: CommandContext, cursor: FSMCursor):
    if cursor.get_state() is None and not cursor.get_data():
        await context.reply(ACTIVE_DIALOG_MISSING_TEXT)
        return

    cursor.clear()
    await context.reply(DIALOG_RESET_TEXT)


@router.on_command("book")
async def book_handler(context: CommandContext, cursor: FSMCursor):
    try:
        rooms = await get_rooms()
    except Exception as exc:
        await context.reply(BOOKING_START_ERROR_TEXT.format(error=exc))
        return

    keyboard = buttons.KeyboardBuilder()
    keyboard.table(
        3,
        *[
            buttons.CallbackButton(
                text=str(room.id),
                payload=f"{BOOKING_ROOM_CALLBACK_PREFIX}{room.id}",
            )
            for room in rooms
        ],
    )

    cursor.change_state(BookingState.WAITING_ROOM)
    cursor.change_data({})
    await context.reply(
        BOOKING_PICK_ROOM_TEXT.format(rooms=format_rooms(rooms)),
        keyboard=keyboard,
    )


@router.on_button_callback(startswith(BOOKING_ROOM_CALLBACK_PREFIX))
async def booking_room_callback_handler(callback: Callback, cursor: FSMCursor):
    raw_room_id = callback.content.removeprefix(BOOKING_ROOM_CALLBACK_PREFIX)
    try:
        room_id = parse_room_id(raw_room_id)
        room = await get_room(room_id)
    except BookingServiceError as exc:
        await callback.answer(notification=str(exc))
        return
    except Exception as exc:
        await callback.answer(notification=ROOM_SELECT_ERROR_TEXT.format(error=exc))
        return

    if room.id == PHONE_ONLY_ROOM_ID:
        cursor.clear()
        if callback.message is not None:
            await callback.message.edit(
                PHONE_ONLY_BOOKING_TEXT,
                format="markdown",
                notify=False,
            )
            return

        await callback.reply(PHONE_ONLY_BOOKING_TEXT, format="markdown")
        return

    keyboard = buttons.KeyboardBuilder()
    keyboard.row(
        buttons.CallbackButton(
            text=TODAY_BUTTON_TEXT.format(date_label=date.today().strftime("%d.%m")),
            payload=f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:{date.today().strftime('%d.%m.%Y')}",
        ),
        buttons.CallbackButton(
            text=TOMORROW_BUTTON_TEXT.format(
                date_label=(date.today() + timedelta(days=1)).strftime("%d.%m")
            ),
            payload=(
                f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:"
                f"{(date.today() + timedelta(days=1)).strftime('%d.%m.%Y')}"
            ),
        ),
    )

    cursor.change_state(BookingState.WAITING_DATE)
    cursor.change_data(
        {
            "room_id": room.id,
            "room_name": room.name,
            "available_slots": [],
        }
    )

    if callback.message is not None:
        await callback.message.edit(
            BOOKING_DATE_PICK_TEXT.format(room_name=room.name),
            keyboard=keyboard,
            notify=False,
        )
        return

    await callback.reply(
        BOOKING_DATE_PICK_TEXT.format(room_name=room.name),
        keyboard=keyboard,
    )


@router.on_button_callback(startswith(BOOKING_DATE_CALLBACK_PREFIX))
async def booking_date_callback_handler(callback: Callback, cursor: FSMCursor):
    try:
        raw_data = callback.content.removeprefix(BOOKING_DATE_CALLBACK_PREFIX)
        room_id_raw, book_date_raw = raw_data.split(":", maxsplit=1)
        room_id = parse_room_id(room_id_raw)
        book_date = parse_booking_date(book_date_raw)
        room = await get_room(room_id)
        if room.id == PHONE_ONLY_ROOM_ID:
            raise BookingServiceError(PHONE_ONLY_BOOKING_TEXT)
        slots = await get_slots(room_id, book_date)
    except BookingServiceError as exc:
        if str(exc) == PHONE_ONLY_BOOKING_TEXT and callback.message is not None:
            cursor.clear()
            await callback.message.edit(str(exc), format="markdown", notify=False)
            return
        await callback.answer(notification=str(exc))
        return
    except Exception as exc:
        await callback.answer(notification=DATE_CHANGE_ERROR_TEXT.format(error=exc))
        return

    cursor.change_data(
        {
            **(cursor.get_data() or {}),
            "room_id": room.id,
            "room_name": room.name,
            "book_date": book_date.strftime("%d.%m.%Y"),
            "available_slots": [slot.model_dump() for slot in slots],
        }
    )
    cursor.change_state(
        BookingState.WAITING_SLOT if slots else BookingState.WAITING_DATE
    )

    text_parts = [
        ROOM_LABEL_TEXT.format(room_name=room.name),
        DATE_LABEL_TEXT.format(date_label=book_date.strftime("%d.%m.%Y")),
        "",
    ]
    if slots:
        text_parts.append(SLOTS_HEADER_TEXT)
        text_parts.append(format_slots(slots))
        text_parts.append("")
        text_parts.append(BOOKING_SLOT_PROMPT_TEXT)
    else:
        text_parts.append(NO_SLOTS_TEXT)
        text_parts.append("")
        text_parts.append(BOOKING_EMPTY_DATE_TEXT)

    keyboard = buttons.KeyboardBuilder()
    keyboard.row(
        buttons.CallbackButton(
            text=PREVIOUS_DATE_BUTTON_TEXT.format(
                date_label=(book_date - timedelta(days=1)).strftime("%d.%m")
            ),
            payload=(
                f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:"
                f"{(book_date - timedelta(days=1)).strftime('%d.%m.%Y')}"
            ),
        ),
        buttons.CallbackButton(
            text=NEXT_DATE_BUTTON_TEXT.format(
                date_label=(book_date + timedelta(days=1)).strftime("%d.%m")
            ),
            payload=(
                f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:"
                f"{(book_date + timedelta(days=1)).strftime('%d.%m.%Y')}"
            ),
        ),
    )

    if callback.message is not None:
        await callback.message.edit(
            "\n".join(text_parts),
            keyboard=keyboard,
            format="markdown",
            notify=False,
        )
        return

    await callback.reply("\n".join(text_parts), keyboard=keyboard, format="markdown")


@router.on_message(state(BookingState.WAITING_ROOM))
async def booking_room_handler(message: Message, cursor: FSMCursor):
    try:
        room_id = parse_room_id(message.content or "")
        room = await get_room(room_id)
    except BookingServiceError as exc:
        await message.reply(str(exc))
        return
    except Exception as exc:
        await message.reply(ROOM_SELECT_ERROR_TEXT.format(error=exc))
        return

    if room.id == PHONE_ONLY_ROOM_ID:
        cursor.clear()
        await message.reply(PHONE_ONLY_BOOKING_TEXT, format="markdown")
        return

    keyboard = buttons.KeyboardBuilder()
    keyboard.row(
        buttons.CallbackButton(
            text=TODAY_BUTTON_TEXT.format(date_label=date.today().strftime("%d.%m")),
            payload=f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:{date.today().strftime('%d.%m.%Y')}",
        ),
        buttons.CallbackButton(
            text=TOMORROW_BUTTON_TEXT.format(
                date_label=(date.today() + timedelta(days=1)).strftime("%d.%m")
            ),
            payload=(
                f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:"
                f"{(date.today() + timedelta(days=1)).strftime('%d.%m.%Y')}"
            ),
        ),
    )

    cursor.change_state(BookingState.WAITING_DATE)
    cursor.change_data(
        {
            "room_id": room.id,
            "room_name": room.name,
            "available_slots": [],
        }
    )
    await message.reply(
        BOOKING_DATE_PICK_TEXT.format(room_name=room.name),
        keyboard=keyboard,
    )


@router.on_message(state(BookingState.WAITING_DATE))
async def booking_date_handler(message: Message, cursor: FSMCursor):
    room_id = (cursor.get_data() or {}).get("room_id")
    if room_id is None:
        cursor.clear()
        await message.reply(BOOKING_STATE_LOST_TEXT, format="markdown")
        return

    try:
        book_date = parse_booking_date(message.content or "")
        room = await get_room(room_id)
        if room.id == PHONE_ONLY_ROOM_ID:
            raise BookingServiceError(PHONE_ONLY_BOOKING_TEXT)
        slots = await get_slots(room_id, book_date)
    except BookingServiceError as exc:
        if str(exc) == PHONE_ONLY_BOOKING_TEXT:
            cursor.clear()
        await message.reply(str(exc))
        return
    except Exception as exc:
        await message.reply(SLOTS_REFRESH_ERROR_TEXT.format(error=exc))
        return

    cursor.change_data(
        {
            **(cursor.get_data() or {}),
            "room_id": room.id,
            "room_name": room.name,
            "book_date": book_date.strftime("%d.%m.%Y"),
            "available_slots": [slot.model_dump() for slot in slots],
        }
    )
    cursor.change_state(
        BookingState.WAITING_SLOT if slots else BookingState.WAITING_DATE
    )

    text_parts = [
        ROOM_LABEL_TEXT.format(room_name=room.name),
        DATE_LABEL_TEXT.format(date_label=book_date.strftime("%d.%m.%Y")),
        "",
    ]
    if slots:
        text_parts.append(SLOTS_HEADER_TEXT)
        text_parts.append(format_slots(slots))
        text_parts.append("")
        text_parts.append(BOOKING_SLOT_PROMPT_TEXT)
    else:
        text_parts.append(NO_SLOTS_TEXT)
        text_parts.append("")
        text_parts.append(BOOKING_EMPTY_DATE_TEXT)

    keyboard = buttons.KeyboardBuilder()
    keyboard.row(
        buttons.CallbackButton(
            text=PREVIOUS_DATE_BUTTON_TEXT.format(
                date_label=(book_date - timedelta(days=1)).strftime("%d.%m")
            ),
            payload=(
                f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:"
                f"{(book_date - timedelta(days=1)).strftime('%d.%m.%Y')}"
            ),
        ),
        buttons.CallbackButton(
            text=NEXT_DATE_BUTTON_TEXT.format(
                date_label=(book_date + timedelta(days=1)).strftime("%d.%m")
            ),
            payload=(
                f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:"
                f"{(book_date + timedelta(days=1)).strftime('%d.%m.%Y')}"
            ),
        ),
    )
    await message.reply("\n".join(text_parts), keyboard=keyboard, format="markdown")


@router.on_message(state(BookingState.WAITING_SLOT))
async def booking_slot_handler(message: Message, cursor: FSMCursor):
    data = cursor.get_data() or {}
    room_id = data.get("room_id")
    available_slots = data.get("available_slots") or []

    if room_id is None:
        cursor.clear()
        await message.reply(BOOKING_STATE_LOST_TEXT, format="markdown")
        return

    try:
        book_date = parse_booking_date(message.content or "")
    except BookingServiceError:
        book_date = None

    if book_date is not None:
        try:
            room = await get_room(room_id)
            if room.id == PHONE_ONLY_ROOM_ID:
                raise BookingServiceError(PHONE_ONLY_BOOKING_TEXT)
            slots = await get_slots(room_id, book_date)
        except BookingServiceError as exc:
            cursor.clear()
            await message.reply(str(exc), format="markdown")
            return
        except Exception as exc:
            await message.reply(SLOTS_REFRESH_ERROR_TEXT.format(error=exc))
            return

        cursor.change_data(
            {
                **data,
                "room_id": room.id,
                "room_name": room.name,
                "book_date": book_date.strftime("%d.%m.%Y"),
                "available_slots": [slot.model_dump() for slot in slots],
            }
        )
        cursor.change_state(
            BookingState.WAITING_SLOT if slots else BookingState.WAITING_DATE
        )

        text_parts = [
            ROOM_LABEL_TEXT.format(room_name=room.name),
            DATE_LABEL_TEXT.format(date_label=book_date.strftime("%d.%m.%Y")),
            "",
        ]
        if slots:
            text_parts.append(SLOTS_HEADER_TEXT)
            text_parts.append(format_slots(slots))
            text_parts.append("")
            text_parts.append(BOOKING_SLOT_PROMPT_TEXT)
        else:
            text_parts.append(NO_SLOTS_TEXT)
            text_parts.append("")
            text_parts.append(BOOKING_EMPTY_DATE_TEXT)

        keyboard = buttons.KeyboardBuilder()
        keyboard.row(
            buttons.CallbackButton(
                text=PREVIOUS_DATE_BUTTON_TEXT.format(
                    date_label=(book_date - timedelta(days=1)).strftime("%d.%m")
                ),
                payload=(
                    f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:"
                    f"{(book_date - timedelta(days=1)).strftime('%d.%m.%Y')}"
                ),
            ),
            buttons.CallbackButton(
                text=NEXT_DATE_BUTTON_TEXT.format(
                    date_label=(book_date + timedelta(days=1)).strftime("%d.%m")
                ),
                payload=(
                    f"{BOOKING_DATE_CALLBACK_PREFIX}{room.id}:"
                    f"{(book_date + timedelta(days=1)).strftime('%d.%m.%Y')}"
                ),
            ),
        )
        await message.reply(
            "\n".join(text_parts),
            keyboard=keyboard,
            format="markdown",
        )
        return

    if not available_slots:
        await message.reply(BOOKING_EMPTY_SLOTS_DATE_TEXT)
        return

    try:
        indexes = [int(value) for value in re.findall(r"\d+", message.content or "")]
        if not indexes:
            raise BookingServiceError("Нужно указать хотя бы один номер слота")

        unique_indexes: list[int] = []
        for index in indexes:
            if index < 1 or index > len(available_slots):
                raise BookingServiceError(
                    f"Слот с номером {index} не найден. Выбери номер из списка."
                )
            if index not in unique_indexes:
                unique_indexes.append(index)
    except BookingServiceError as exc:
        await message.reply(str(exc))
        return

    selected_slots = [available_slots[index - 1] for index in unique_indexes]
    cursor.change_data({**data, "selected_slots": selected_slots})
    cursor.change_state(BookingState.WAITING_NAME)
    await message.reply(BOOKING_NAME_TEXT)


@router.on_message(state(BookingState.WAITING_NAME))
async def booking_name_handler(message: Message, cursor: FSMCursor):
    fullname = (message.content or "").strip()
    if len(fullname) < 2:
        await message.reply(BOOKING_NAME_SHORT_TEXT)
        return

    cursor.change_data({**(cursor.get_data() or {}), "fullname": fullname})
    cursor.change_state(BookingState.WAITING_PHONE)
    await message.reply(BOOKING_PHONE_TEXT)


@router.on_message(state(BookingState.WAITING_PHONE))
async def booking_phone_handler(message: Message, cursor: FSMCursor):
    phone = (message.content or "").strip()
    if not PHONE_PATTERN.fullmatch(phone):
        await message.reply(BOOKING_PHONE_INVALID_TEXT, format="markdown")
        return

    cursor.change_data({**(cursor.get_data() or {}), "phone": phone})
    cursor.change_state(BookingState.WAITING_COMMENT)
    keyboard = buttons.KeyboardBuilder()
    keyboard.row(buttons.MessageButton(text=NO_COMMENT_BUTTON_TEXT))
    await message.reply(BOOKING_COMMENT_TEXT, keyboard=keyboard, format="markdown")


@router.on_message(state(BookingState.WAITING_COMMENT))
async def booking_comment_handler(message: Message, cursor: FSMCursor):
    data = cursor.get_data() or {}
    raw_comment = (message.content or "").strip()
    comment = "" if raw_comment.lower() in COMMENT_SKIP_VALUES else raw_comment
    try:
        selected_slots = [
            Slot.model_validate(slot) for slot in data.get("selected_slots", [])
        ]
        if not selected_slots:
            raise BookingServiceError("Не выбраны слоты для брони")
    except BookingServiceError as exc:
        await message.reply(str(exc))
        return
    except KeyError:
        cursor.clear()
        await message.reply(BOOKING_STATE_LOST_TEXT, format="markdown")
        return

    cursor.change_data({**data, "comment": comment})
    cursor.change_state(BookingState.WAITING_CONFIRM)
    total_price = sum(slot["price"] for slot in data["selected_slots"])

    keyboard = buttons.KeyboardBuilder()
    keyboard.row(
        buttons.CallbackButton(
            text=BOOKING_CONFIRM_BUTTON_TEXT,
            payload=BOOKING_CONFIRM_SUBMIT_CALLBACK,
            intent="positive",
        ),
        buttons.CallbackButton(
            text=BOOKING_CONFIRM_CANCEL_BUTTON_TEXT,
            payload=BOOKING_CONFIRM_CANCEL_CALLBACK,
            intent="negative",
        ),
    )
    await message.reply(
        BOOKING_CONFIRM_TEXT.format(
            room_name=data.get("room_name", f"Комната #{data['room_id']}"),
            book_date=data["book_date"],
            slot_lines="\n".join(
                f"- {slot['value']}" for slot in data["selected_slots"]
            ),
            total_price=total_price,
            fullname=data["fullname"],
            phone=data["phone"],
            comment=comment or "без комментария",
        ),
        keyboard=keyboard,
        format="markdown",
    )


@router.on_button_callback(BOOKING_CONFIRM_SUBMIT_CALLBACK)
async def booking_confirm_submit_handler(callback: Callback, cursor: FSMCursor):
    data = cursor.get_data() or {}
    if cursor.get_state() != BookingState.WAITING_CONFIRM:
        await callback.answer(notification=BOOKING_CONFIRM_STATE_TEXT)
        return

    msg = await callback.message.send("В обработке...")
    await callback.message.delete()
    try:
        selected_slots = [
            Slot.model_validate(slot) for slot in data.get("selected_slots", [])
        ]
        if not selected_slots:
            raise BookingServiceError("Не выбраны слоты для брони")

        await create_booking(
            room_id=data["room_id"],
            book_date=parse_booking_date(data["book_date"]),
            slots=selected_slots,
            fullname=data["fullname"],
            phone=data["phone"],
            comment=data.get("comment", ""),
        )
    except BookingServiceError as exc:
        await callback.answer(notification=str(exc))
        return
    except KeyError:
        cursor.clear()
        if callback.message is not None:
            await callback.message.edit(
                BOOKING_STATE_LOST_TEXT, format="markdown", notify=False
            )
        else:
            await callback.reply(BOOKING_STATE_LOST_TEXT, format="markdown")
        return
    except Exception as exc:
        cursor.clear()
        if callback.message is not None:
            await callback.message.edit(
                BOOKING_FAILED_TEXT.format(error=exc),
                format="markdown",
                notify=False,
            )
        else:
            await callback.reply(
                BOOKING_FAILED_TEXT.format(error=exc), format="markdown"
            )
        return

    slot_lines = "\n".join(f"- {slot['value']}" for slot in data["selected_slots"])
    total_price = sum(slot["price"] for slot in data["selected_slots"])
    room_name = data.get("room_name", f"Комната #{data['room_id']}")
    success_text = BOOKING_SUCCESS_TEXT.format(
        room_name=room_name,
        book_date=data["book_date"],
        slot_lines=slot_lines,
        total_price=total_price,
        fullname=data["fullname"],
        phone=data["phone"],
        comment=data.get("comment") or "без комментария",
    )
    cursor.clear()
    await msg.edit(success_text, format="markdown", notify=False)


@router.on_button_callback(BOOKING_CONFIRM_CANCEL_CALLBACK)
async def booking_confirm_cancel_handler(callback: Callback, cursor: FSMCursor):
    cursor.clear()
    await callback.message.send(BOOKING_CONFIRM_CANCELLED_TEXT, notify=False)
    await callback.message.delete()
    return
