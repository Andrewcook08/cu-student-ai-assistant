"""Unit tests for chat_service.core.output_validator (SEC-003 / CUAI-62).

All validation is performed locally — no external services or mocks required.
"""

from __future__ import annotations

from chat_service.core.output_validator import validate_output
from shared.schemas import ChatResponse

# ─── Schema enforcement: CourseCard ─────────────────────────────────────


def test_valid_course_cards_pass_through() -> None:
    cards = [{"code": "CSCI 3104", "title": "Algorithms"}]
    result = validate_output("Here are some courses.", cards)
    assert len(result.structured_data) == 1
    assert result.structured_data[0]["code"] == "CSCI 3104"
    assert result.structured_data[0]["title"] == "Algorithms"
    assert result.invalid_cards_stripped == 0


def test_invalid_card_missing_code_stripped() -> None:
    cards = [{"title": "Algorithms"}]
    result = validate_output("Here are some courses.", cards)
    assert result.structured_data == []
    assert result.invalid_cards_stripped == 1


def test_invalid_card_missing_title_stripped() -> None:
    cards = [{"code": "CSCI 3104"}]
    result = validate_output("Here are some courses.", cards)
    assert result.structured_data == []
    assert result.invalid_cards_stripped == 1


def test_mixed_valid_invalid_cards() -> None:
    cards = [
        {"code": "CSCI 3104", "title": "Algorithms"},
        {"title": "No Code Card"},
        {"code": "CSCI 2270", "title": "Data Structures"},
        {"code": "ONLY_CODE"},
    ]
    result = validate_output("Here are some courses.", cards)
    assert len(result.structured_data) == 2
    assert result.invalid_cards_stripped == 2


def test_empty_structured_data_returns_empty() -> None:
    result = validate_output("No courses found.", [])
    assert result.structured_data == []
    assert result.invalid_cards_stripped == 0


def test_extra_fields_on_card_stripped() -> None:
    cards = [{"code": "CSCI 3104", "title": "Algorithms", "secret_field": "hack"}]
    result = validate_output("Here are some courses.", cards)
    assert len(result.structured_data) == 1
    assert "secret_field" not in result.structured_data[0]


# ─── Schema enforcement: Action ──────────────────────────────────────────


def test_valid_actions_pass_through() -> None:
    actions = [{"type": "enroll", "label": "Enroll Now"}]
    result = validate_output("Reply.", [], actions)
    assert len(result.suggested_actions) == 1
    assert result.suggested_actions[0]["type"] == "enroll"
    assert result.suggested_actions[0]["label"] == "Enroll Now"
    assert result.invalid_actions_stripped == 0


def test_invalid_action_missing_type_stripped() -> None:
    actions = [{"label": "Enroll Now"}]
    result = validate_output("Reply.", [], actions)
    assert result.suggested_actions == []
    assert result.invalid_actions_stripped == 1


def test_invalid_action_missing_label_stripped() -> None:
    actions = [{"type": "enroll"}]
    result = validate_output("Reply.", [], actions)
    assert result.suggested_actions == []
    assert result.invalid_actions_stripped == 1


def test_none_suggested_actions_returns_empty() -> None:
    result = validate_output("Reply.", [], None)
    assert result.suggested_actions == []
    assert result.invalid_actions_stripped == 0


# ─── PII scanning ───────────────────────────────────────────────────────


def test_email_redacted() -> None:
    result = validate_output("contact john@example.com for help.", [])
    assert "[REDACTED]" in result.reply
    assert "john@example.com" not in result.reply
    assert result.pii_detected is True
    assert result.pii_redacted_count >= 1


def test_cu_boulder_email_redacted() -> None:
    result = validate_output("Email student@colorado.edu with questions.", [])
    assert "student@colorado.edu" not in result.reply
    assert "[REDACTED]" in result.reply
    assert result.pii_detected is True


def test_student_id_7_digit_redacted() -> None:
    result = validate_output("Your ID 1234567 is on file.", [])
    assert "1234567" not in result.reply
    assert "[REDACTED]" in result.reply
    assert result.pii_detected is True


def test_student_id_9_digit_redacted() -> None:
    result = validate_output("Your ID 123456789 is on file.", [])
    assert "123456789" not in result.reply
    assert "[REDACTED]" in result.reply
    assert result.pii_detected is True


def test_phone_number_redacted() -> None:
    result = validate_output("Call (303) 555-1234 to register.", [])
    assert "(303) 555-1234" not in result.reply
    assert "[REDACTED]" in result.reply
    assert result.pii_detected is True


def test_ssn_redacted() -> None:
    result = validate_output("SSN 123-45-6789 must not appear.", [])
    assert "123-45-6789" not in result.reply
    assert "[REDACTED]" in result.reply
    assert result.pii_detected is True


def test_multiple_pii_all_redacted() -> None:
    text = "Email john@example.com or call (303) 555-1234, SSN 123-45-6789."
    result = validate_output(text, [])
    assert "john@example.com" not in result.reply
    assert "(303) 555-1234" not in result.reply
    assert "123-45-6789" not in result.reply
    assert result.pii_detected is True
    assert result.pii_redacted_count >= 3


def test_no_pii_unchanged() -> None:
    text = "Please register for CSCI 3104 before the deadline."
    result = validate_output(text, [])
    assert result.reply == text
    assert result.pii_detected is False
    assert result.pii_redacted_count == 0


def test_course_number_not_false_positive() -> None:
    result = validate_output("Enroll in CSCI 3104 this semester.", [])
    assert "CSCI 3104" in result.reply
    assert result.pii_detected is False


def test_four_digit_year_not_flagged() -> None:
    result = validate_output("Fall 2024 registration opens Monday.", [])
    assert "2024" in result.reply
    assert result.pii_detected is False


def test_five_digit_zip_not_flagged() -> None:
    result = validate_output("The campus ZIP is 80309.", [])
    assert "80309" in result.reply
    assert result.pii_detected is False


def test_dollar_amount_not_flagged() -> None:
    result = validate_output("Tuition is $1234567 per year.", [])
    assert "$1234567" in result.reply
    assert result.pii_detected is False


def test_pii_in_course_card_attributes_redacted() -> None:
    cards = [
        {
            "code": "CSCI 3104",
            "title": "Algorithms",
            "attributes": ["Writing Intensive", "Contact admin@example.com"],
        }
    ]
    result = validate_output("See attributes.", cards)
    assert len(result.structured_data) == 1
    attrs = result.structured_data[0]["attributes"]
    assert "admin@example.com" not in attrs[1]
    assert "[REDACTED]" in attrs[1]
    assert attrs[0] == "Writing Intensive"
    assert result.pii_detected is True


def test_pii_in_course_card_description_redacted() -> None:
    cards = [
        {
            "code": "CSCI 3104",
            "title": "Algorithms",
            "description": "Contact prof@example.com for syllabus.",
        }
    ]
    result = validate_output("See description.", cards)
    assert len(result.structured_data) == 1
    assert "prof@example.com" not in result.structured_data[0].get("description", "")
    assert "[REDACTED]" in result.structured_data[0]["description"]
    assert result.pii_detected is True


# ─── Scope check ────────────────────────────────────────────────────────


def test_shell_command_detected() -> None:
    result = validate_output("You can run sudo apt-get install python.", [])
    assert result.scope_violation_detected is True


def test_sql_injection_detected() -> None:
    result = validate_output("Someone tried DROP TABLE users in the DB.", [])
    assert result.scope_violation_detected is True


def test_normal_academic_content_not_flagged() -> None:
    result = validate_output("You can drop this course before the deadline.", [])
    assert result.scope_violation_detected is False


def test_lowercase_sql_detected() -> None:
    result = validate_output("Try delete from users where id=1.", [])
    assert result.scope_violation_detected is True


def test_scope_violation_in_structured_data_detected() -> None:
    cards = [
        {
            "code": "CSCI 3104",
            "title": "Algorithms",
            "description": "Run sudo apt-get install to set up the lab.",
        }
    ]
    result = validate_output("Here are your courses.", cards)
    assert result.scope_violation_detected is True


def test_scope_flag_does_not_strip_reply() -> None:
    text = "You can run sudo apt-get install python."
    result = validate_output(text, [])
    assert result.scope_violation_detected is True
    assert result.reply == text


# ─── Full integration ───────────────────────────────────────────────────


def test_clean_response_passes_through() -> None:
    cards = [{"code": "CSCI 3104", "title": "Algorithms", "credits": "3"}]
    actions = [{"type": "enroll", "label": "Enroll Now"}]
    reply = "Here are courses for you."
    result = validate_output(reply, cards, actions)
    assert result.reply == reply
    assert len(result.structured_data) == 1
    assert len(result.suggested_actions) == 1
    assert result.pii_detected is False
    assert result.pii_redacted_count == 0
    assert result.scope_violation_detected is False
    assert result.invalid_cards_stripped == 0
    assert result.invalid_actions_stripped == 0


def test_pii_and_invalid_card_combined() -> None:
    cards = [
        {"code": "CSCI 3104", "title": "Algorithms"},
        {"title": "Missing code card"},
    ]
    reply = "Contact admin@colorado.edu for more info."
    result = validate_output(reply, cards)
    assert result.invalid_cards_stripped == 1
    assert len(result.structured_data) == 1
    assert "admin@colorado.edu" not in result.reply
    assert result.pii_detected is True


def test_result_fields_correct_types() -> None:
    result = validate_output("Some reply.", [{"code": "CSCI 1300", "title": "Intro"}])
    assert isinstance(result.reply, str)
    assert isinstance(result.structured_data, list)
    assert isinstance(result.suggested_actions, list)
    assert isinstance(result.pii_detected, bool)
    assert isinstance(result.pii_redacted_count, int)
    assert isinstance(result.scope_violation_detected, bool)
    assert isinstance(result.invalid_cards_stripped, int)
    assert isinstance(result.invalid_actions_stripped, int)


def test_validation_result_produces_valid_chat_response() -> None:
    cards = [{"code": "CSCI 3104", "title": "Algorithms"}]
    actions = [{"type": "view", "label": "View Details"}]
    result = validate_output("Here are your results.", cards, actions)

    response = ChatResponse(
        reply=result.reply,
        structured_data=result.structured_data or None,
        suggested_actions=result.suggested_actions or None,
    )
    assert response.reply == result.reply
