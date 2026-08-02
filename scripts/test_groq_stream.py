import sys

from groq import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)

from app.providers.llm_groq import (
    GroqProviderError,
    run_streaming_test,
)


DEFAULT_TEST_MESSAGE = (
    "A customer says: I want to promote my clothing brand. "
    "Reply as a professional voice agent and ask the next question."
)


def main() -> int:
    """Run the Phase 2 Groq streaming verification."""

    message = " ".join(sys.argv[1:]).strip()

    if not message:
        message = DEFAULT_TEST_MESSAGE

    try:
        run_streaming_test(message)
        return 0

    except AuthenticationError:
        print("")
        print("[GROQ] TEST FAILED")
        print("[ERROR] Groq rejected the API key.")
        print(
            "[FIX] Check GROQ_API_KEY inside the .env file. "
            "Do not add extra spaces."
        )
        return 1

    except RateLimitError as error:
        print("")
        print("[GROQ] TEST FAILED")
        print("[ERROR] Groq rate limit or quota was reached.")
        print(f"[DETAIL] {error}")
        print(
            "[FIX] Wait briefly, check your Groq limits, "
            "and run the test again."
        )
        return 1

    except APIConnectionError as error:
        print("")
        print("[GROQ] TEST FAILED")
        print("[ERROR] Could not connect to Groq.")
        print(f"[DETAIL] {error}")
        print(
            "[FIX] Check your internet connection, firewall "
            "and VPN settings."
        )
        return 1

    except APIStatusError as error:
        print("")
        print("[GROQ] TEST FAILED")
        print(
            f"[ERROR] Groq returned HTTP status "
            f"{error.status_code}."
        )
        print(f"[DETAIL] {error}")
        print(
            "[FIX] Check the model name and Groq account status."
        )
        return 1

    except GroqProviderError as error:
        print("")
        print("[GROQ] TEST FAILED")
        print(f"[ERROR] {error}")
        return 1

    except Exception as error:
        print("")
        print("[GROQ] TEST FAILED")
        print(
            f"[UNEXPECTED ERROR] "
            f"{type(error).__name__}: {error}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())