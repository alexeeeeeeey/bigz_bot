from pydantic import BaseModel


class Room(BaseModel):
    id: int
    name: str


class Slot(BaseModel):
    value: str
    price: int
