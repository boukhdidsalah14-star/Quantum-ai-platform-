from app.telegram_bot import _price_line, build_application


def test_telegram_bot_registers_read_only_market_commands():
    application = build_application("123456:TEST_TOKEN")
    callbacks = {
        handler.callback.__name__
        for handlers in application.handlers.values()
        for handler in handlers
    }
    assert {"start", "help_command", "status", "markets", "price"} <= callbacks

def test_telegram_price_line_formats_public_quote():
    line = _price_line({
        "symbol": "BTCUSDT",
        "price": "65000.125",
        "change_percent": "1.25",
    })
    assert line == "BTCUSDT: $65,000.1250 (+1.25%)"


def test_telegram_price_line_formats_negative_change():
    line = _price_line({
        "symbol": "ETHUSDT",
        "price": "2500",
        "change_percent": "-0.75",
    })
    assert line.endswith("(-0.75%)")
