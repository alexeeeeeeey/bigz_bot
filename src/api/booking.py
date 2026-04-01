import re
from datetime import date

from bs4 import BeautifulSoup as BS

from api import BaseApi
from api.schemas import Room, Slot

PRICE_PATTERN = re.compile(r"₽\s*(\d+)")


class BookingApi(BaseApi):
    async def get_rooms(self) -> list[Room]:
        response = await self.get("/book")
        soup = BS(await response.text(), features="html.parser")
        select = soup.find("select", id="room")
        if select is None:
            raise RuntimeError(
                "Не удалось найти список комнат на странице бронирования"
            )

        return [
            Room(id=option["value"], name=option.get_text(strip=True))
            for option in select.find_all("option")
            if option.get("value")
        ]

    async def get_slots(self, room_id: int, book_date: date) -> list[Slot]:
        response = await self.get(
            "/book", params={"room": room_id, "date": book_date.strftime("%Y-%m-%d")}
        )
        soup = BS(await response.text(), features="html.parser")
        slots: list[Slot] = []

        for slot_node in soup.select("div.form-check"):
            input_node = slot_node.find("input", attrs={"name": "time"})
            label_node = slot_node.find("label", class_="form-check-label")
            if input_node is None or label_node is None:
                continue

            value = input_node.get("value")
            if not value or "-" not in value:
                continue

            price_match = PRICE_PATTERN.search(label_node.get_text(" ", strip=True))
            if price_match is None:
                continue

            slots.append(
                Slot(
                    value=value,
                    price=int(price_match.group(1)),
                )
            )

        return slots

    async def book(
        self,
        room_id: int,
        book_date: date,
        slots: list[Slot],
        fullname: str,
        phone: str,
        comment: str,
    ) -> str:
        slot_values = [slot.value for slot in slots]
        if not slot_values:
            raise ValueError("Нужно передать хотя бы один слот для бронирования")

        date_value = book_date.strftime("%Y-%m-%d")
        params = {
            "room": room_id,
            "date": date_value,
            "time": ",".join(slot_values),
        }
        response = await self.get("/book", params=params)

        soup = BS(await response.text(), features="html.parser")
        csrf_input = soup.find("input", {"name": "_token"})
        csrf = csrf_input.get("value", None) if csrf_input is not None else None
        if csrf is None:
            raise RuntimeError("Не удалось получить CSRF-токен")

        form_data: list[tuple[str, str]] = [
            ("_token", csrf),
            ("room", str(room_id)),
            ("date", date_value),
            ("name", fullname),
            ("phone", phone),
            ("comment", comment),
            ("rules", "on"),
            ("submit", ""),
            ("time", ",".join(slot_values)),
        ]

        response = await self.post("/book", data=form_data)
        return await response.text()
