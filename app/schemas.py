from typing import List
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=3, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=15)
    password: str = Field(min_length=8, max_length=50)



class PlannerRequest(BaseModel):
    destination: str = Field(min_length=2, max_length=80)
    days: int = Field(ge=1, le=14)
    budget: float = Field(gt=0)
    interests: List[str] = []


class ExpenseRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=50)
    amount: float = Field(gt=0)
    destination: str = "General"


class StoryMediaItem(BaseModel):
    media_url: str = Field(min_length=1, max_length=300)
    media_type: str = Field(min_length=1, max_length=20)


class StoryRequest(BaseModel):
    author: str = Field(min_length=2, max_length=80)
    destination: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=4, max_length=160)
    content: str = Field(min_length=20, max_length=3000)
    media_url: str | None = Field(default=None, max_length=300)
    media_type: str | None = Field(default=None, max_length=20)
    media_items: list[StoryMediaItem] = Field(default_factory=list, max_length=10)


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
