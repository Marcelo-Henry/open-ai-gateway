# -*- coding: utf-8 -*-

import json

from kiro.parsers import AwsEventStreamParser


class TestAwsEventStreamParserToolMerging:
    def test_parses_tool_start_even_when_name_is_not_first_key(self):
        parser = AwsEventStreamParser()

        chunk = (
            b"\x00\x01binary-prefix"
            b'{"toolUseId":"tool_123","name":"Bash","input":"{\\"command\\":\\"ls\\"}"}'
        )
        events = parser.feed(chunk)

        assert len(events) == 1
        assert events[0]["type"] == "tool_start"
        assert events[0]["data"]["id"] == "tool_123"
        assert events[0]["data"]["name"] == "Bash"
        assert events[0]["data"]["input"] == '{"command":"ls"}'

    def test_cumulative_tool_input_does_not_corrupt_json_arguments(self):
        parser = AwsEventStreamParser()

        events_start = parser.feed(
            b'{"toolUseId":"call_1","name":"search","input":"{\\"query\\":\\"test\\"}"}'
        )
        assert events_start[0]["type"] == "tool_start"
        assert events_start[0]["data"]["input"] == '{"query":"test"}'

        # Provider sends a cumulative snapshot instead of strict delta
        events_delta = parser.feed(
            b'{"input":"{\\"query\\":\\"test\\",\\"limit\\":5}"}'
        )
        assert events_delta[0]["type"] == "tool_input"
        assert events_delta[0]["data"]["input"] == ',"limit":5}'

        events_stop = parser.feed(b'{"stop":true}')
        assert events_stop[0]["type"] == "tool_stop"

        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1

        parsed_args = json.loads(tool_calls[0]["function"]["arguments"])
        assert parsed_args == {"query": "test", "limit": 5}
