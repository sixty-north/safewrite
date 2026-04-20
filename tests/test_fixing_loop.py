"""Tests for FixingLoop."""

from safewrite import FixingLoop, FixingLoopStatus


class TestFixingLoop:
    async def test_fixing_loop_already_valid(self):
        def validate(content):
            return []

        loop = FixingLoop(max_attempts=3)
        result = await loop.run(
            content="valid content",
            validate_fn=validate,
            document_type="test",
        )

        assert result.status == FixingLoopStatus.ALREADY_VALID
        assert result.attempts == 0

    async def test_fixing_loop_success_after_repair(self):
        call_count = [0]

        def validate(content):
            call_count[0] += 1
            if call_count[0] == 1:
                return ["Initial error"]
            return []

        async def repair(content, errors, doc_type):
            return "repaired content"

        loop = FixingLoop(max_attempts=3)
        result = await loop.run(
            content="broken content",
            validate_fn=validate,
            document_type="test",
            repair_fn=repair,
        )

        assert result.status == FixingLoopStatus.SUCCESS
        assert result.attempts == 1
        assert result.content == "repaired content"

    async def test_fixing_loop_fails_after_max_attempts(self):
        def validate(content):
            return ["Persistent error"]

        async def repair(content, errors, doc_type):
            return content

        loop = FixingLoop(max_attempts=3)
        result = await loop.run(
            content="broken content",
            validate_fn=validate,
            document_type="test",
            repair_fn=repair,
        )

        assert result.status == FixingLoopStatus.FAILED
        assert result.attempts == 3
        assert "Persistent error" in result.final_errors

    async def test_fixing_loop_no_repair_fn(self):
        def validate(content):
            return ["Error"]

        loop = FixingLoop(max_attempts=3)
        result = await loop.run(
            content="broken content",
            validate_fn=validate,
            document_type="test",
            repair_fn=None,
        )

        assert result.status == FixingLoopStatus.FAILED
        assert result.attempts == 0
