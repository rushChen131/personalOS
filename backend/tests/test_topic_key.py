"""Topic bucketing: the key that decides which statements accumulate together.

A wrong key is invisible at write time and only shows up later as either a
Memory promoted from unrelated evidence (false merge) or a topic that never
reaches the §83 threshold (over-split). Both directions are asserted here.
"""

from __future__ import annotations

import unittest

from tests._env import configure

configure()

from app.services.memory_engine import _normalize, _topic_key  # noqa: E402


def topic(text: str) -> str:
    return _topic_key(_normalize(text))


class TopicKeyTest(unittest.TestCase):
    def test_one_entity_is_one_bucket_across_writings(self) -> None:
        """Spaced, unspaced and English writings of one entity must agree."""
        for text in (
            "我喜欢用 Rust 写后端",
            "I prefer Rust",
            "我喜欢用rust写后端",
            "我一直用 Rust 做实验",
        ):
            self.assertEqual(topic(text), "rust", text)

    def test_entities_containing_digits_do_not_merge(self) -> None:
        """`str.isalpha()` used to reject these and bucket them on the verb."""
        cases = {
            "我习惯用 gpt4 写文案。": "gpt4",
            "我喜欢用 gpt4 写文案。": "gpt4",
            "我习惯用 qwen2 写文案。": "qwen2",
            "我习惯用 Python3 处理数据。": "python3",
            "我一直在用 v2ray 做代理。": "v2ray",
        }
        for text, expected in cases.items():
            self.assertEqual(topic(text), expected, text)

        # The two failure modes this guards against.
        self.assertNotEqual(topic("我习惯用 gpt4 写文案。"), topic("我习惯用 qwen2 写文案。"))
        self.assertEqual(topic("我习惯用 gpt4 写文案。"), topic("我喜欢用 gpt4 写文案。"))

    def test_opener_only_token_does_not_become_the_topic(self) -> None:
        """`我用` peels down to nothing, so the object must supply the key."""
        cases = {
            "我用 飞书 写文档。": "飞书",
            "我用 微信 聊天。": "微信",
            "我用 钉钉 打卡。": "钉钉",
            "我用 键盘 打字。": "键盘",
            "我用 python 写脚本。": "python",
        }
        for text, expected in cases.items():
            self.assertEqual(topic(text), expected, text)

        keys = {topic(text) for text in cases}
        self.assertEqual(len(keys), len(cases), f"distinct objects collapsed into {keys}")

    def test_unsegmented_and_segmented_forms_agree(self) -> None:
        """A journal written without spaces must not land in its own bucket."""
        self.assertEqual(topic("我通常在周末读书"), topic("我喜欢用 读书"))
        self.assertEqual(topic("我通常在周末读书"), "读书")

    def test_a_lone_opener_still_gets_a_stable_bucket(self) -> None:
        """Nothing to bucket on must not mean dropping the statement."""
        self.assertEqual(topic("我喜欢"), "我喜欢")
        self.assertEqual(topic("我习惯"), "我习惯")
        self.assertTrue(topic("我喜欢"))

    def test_a_bare_number_never_beats_a_real_entity(self) -> None:
        """Digits alone are not an entity; a letter is still required."""
        self.assertEqual(topic("我喜欢用 Rust 42"), "rust")
        self.assertEqual(topic("我用 Rust 2026"), "rust")


if __name__ == "__main__":
    unittest.main()
