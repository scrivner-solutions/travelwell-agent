import os
import sys
import pytest

# Load env variables manually from backend/.env before importing ADK modules
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/.env"))
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from google.adk.runners import InMemoryRunner
from google.genai import types
from app.agent import app

@pytest.mark.asyncio
async def test_day_pass_under_5_dollar_prefix():
    """Verify that 'under $5' is correctly parsed and triggers impossible constraints."""
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(app_name="app", user_id="test_user")
    
    response_text = ""
    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text="I'll be in downtown Chicago tomorrow from 6-9 PM. Day pass under $5. I prefer a treadmill and need showers.")]
        ),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    response_text += part.text
                    
    assert "No option satisfies all mandatory constraints" in response_text
    assert "Planet Fitness" in response_text
    assert "YMCA" in response_text
    assert "Alternative" in response_text
    # Ensure numeric scores are removed
    assert "/10" not in response_text

@pytest.mark.asyncio
async def test_day_pass_under_5_dollar_suffix():
    """Verify that 'under 5$' is correctly parsed and triggers impossible constraints."""
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(app_name="app", user_id="test_user")
    
    response_text = ""
    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text="I'll be in downtown Chicago tomorrow from 6-9 PM. Day pass under 5$. I prefer a treadmill and need showers.")]
        ),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    response_text += part.text
                    
    assert "No option satisfies all mandatory constraints" in response_text

@pytest.mark.asyncio
async def test_less_than_5_dollars():
    """Verify that 'less than $5' is correctly parsed and triggers impossible constraints."""
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(app_name="app", user_id="test_user")
    
    response_text = ""
    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text="I'll be in downtown Chicago tomorrow from 6-9 PM. Willing to pay less than $5. I prefer a treadmill and need showers.")]
        ),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    response_text += part.text
                    
    assert "No option satisfies all mandatory constraints" in response_text

@pytest.mark.asyncio
async def test_incomplete_budget():
    """Verify that an incomplete/ambiguous budget like 'under' asks for clarification instead of defaulting."""
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(app_name="app", user_id="test_user")
    
    response_text = ""
    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text="I'll be in downtown Chicago tomorrow from 6-9 PM. Budget is under. I prefer a treadmill and need showers.")]
        ),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    response_text += part.text
                    
    # The agent should ask for clarification regarding budget, not proceed to list facilities
    assert "ymca" not in response_text.lower() and "fitness" not in response_text.lower()
    assert any(keyword in response_text.lower() for keyword in ["budget", "clarify", "specify", "how much", "what is", "under", "amount", "limit"])

@pytest.mark.asyncio
async def test_no_budget_provided():
    """Verify that when no budget is specified, the agent runs with unlimited budget and recommends the YMCA as eligible."""
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(app_name="app", user_id="test_user")
    
    response_text = ""
    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text="I'll be in downtown Chicago tomorrow from 6-9 PM. I have a YMCA membership, prefer a pool or treadmill, need showers.")]
        ),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    response_text += part.text
                    
    assert "No option satisfies all mandatory constraints" not in response_text
    assert "Downtown Chicago YMCA" in response_text
    assert "Eligible" in response_text
    assert "Excellent Match" in response_text
