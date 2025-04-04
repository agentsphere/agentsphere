from app.services.llm_wrapper import update_messages

def test_update_messages_with_placeholders():
    messages = [
        {"content": "Hello {name1}, {name}!"},
        {"content": "Your age is {age}."}
    ]
    callables = {
        "name": lambda: "Alice",
        "age": lambda: 30
    }

    update_messages(messages, callables)

    assert messages[0]["content"] == "Hello {name1}, Alice!"
    assert messages[1]["content"] == "Your age is 30."

def test_update_messages_without_placeholders():
    messages = [
        {"content": "Hello, world!"},
        {"content": "No placeholders here."}
    ]
    callables = {
        "name": lambda: "Alice",
        "age": lambda: 30
    }

    update_messages(messages, callables)

    assert messages[0]["content"] == "Hello, world!"
    assert messages[1]["content"] == "No placeholders here."

def test_update_messages_with_empty_callables():
    messages = [
        {"content": "Hello, {name}!"},
        {"content": "Your age is {age}."}
    ]
    callables = {}

    update_messages(messages, callables)

    assert messages[0]["content"] == "Hello, {name}!"
    assert messages[1]["content"] == "Your age is {age}."