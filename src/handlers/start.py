from aiomax import BotStartPayload, CommandContext, Router
from sqlalchemy import select

from core.db import get_session
from models.user import User

router = Router()

START_TEXT = (
    "Привет!\n\n"
    "Я помогаю с бронированием студии Big-Z.\n\n"
    "Команды:\n"
    "/rooms - показать список комнат\n"
    "/book - начать пошаговое бронирование\n"
    "/cancel - сбросить текущий диалог"
)


HELP_TEXT = (
    "Команды:\n"
    "/rooms - показать список комнат\n"
    "/book - начать пошаговое бронирование\n"
    "/cancel - сбросить текущий диалог"
)


@router.on_bot_start()
async def on_bot_start(payload: BotStartPayload):
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == payload.user.user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                telegram_id=payload.user.user_id,
                username=payload.user.username,
                first_name=payload.user.first_name,
                last_name=payload.user.last_name,
            )
            session.add(user)
        else:
            user.username = payload.user.username
            user.first_name = payload.user.first_name
            user.last_name = payload.user.last_name

        await session.commit()

    await payload.send(START_TEXT)


@router.on_command("start")
@router.on_command("help")
async def start_command(context: CommandContext):
    await context.reply(HELP_TEXT)
