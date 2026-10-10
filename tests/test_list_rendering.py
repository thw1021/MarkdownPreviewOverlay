#!/usr/bin/env python3
import os
import re
import sys
import unittest

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from overlay.md_render import (
    apply_render_settings,
    css_font_family,
    normalize_list_indentation,
    render_markdown_tables_as_html,
    render_ordered_lists,
)


class TestTableLayout(unittest.TestCase):
    """Test the width budget, centering and font of the minihtml table grid."""

    def _rows(self, text, max_width=60, font_family='monospace'):
        out = render_markdown_tables_as_html(text, max_width, font_family=font_family)
        return out, re.findall(r'<div class="visual-row">(.*?)</div>', out)

    def test_narrow_table_is_centered_inside_its_box(self):
        _, rows = self._rows("| a | b |\n|---|---|\n| 1 | 2 |\n")
        self.assertTrue(rows)
        for row in rows:
            cells = re.sub(r'<[^>]+>', '', row)
            # 11-column grid (two 3-wide cells plus the divider) in a 60 budget.
            self.assertEqual(len(cells), 35)
            self.assertEqual(60 - len(cells), 25)
            self.assertEqual(len(cells) - len(cells.lstrip(' ')), 25)

    def test_column_divider_sits_on_the_column_boundary(self):
        _, rows = self._rows("| a | b |\n|---|---|\n| 1 | 2 |\n")
        for row in rows:
            self.assertIn('<span class="tsep">│</span>', row)
        plain = [re.sub(r'<[^>]+>', '', r) for r in rows]
        self.assertEqual({c.index('│') for c in plain}, {plain[0].index('│')})

    def test_divider_can_be_switched_off(self):
        out = render_markdown_tables_as_html(
            "| a | b |\n|---|---|\n| 1 | 2 |\n", 60, column_separator='')
        self.assertNotIn('│', out)

    def test_wide_table_fills_the_budget_without_gutters(self):
        text = "| {} | {} |\n|---|---|\n| {} | {} |\n".format('a' * 40, 'b' * 40, 'c' * 40, 'd' * 40)
        _, rows = self._rows(text, max_width=60)
        widths = {len(re.sub(r'<[^>]+>', '', r)) for r in rows}
        self.assertEqual(widths, {60})

    def test_font_family_reaches_the_grid_css(self):
        out, _ = self._rows("| a |\n|---|\n| 1 |\n", font_family='"Maple Mono", monospace')
        self.assertIn('.table{color:var(--foreground);font-family:"Maple Mono", monospace;', out)
        self.assertIn('.table code{font-family:"Maple Mono", monospace;', out)
        self.assertNotIn('{family}', out)

    def test_grid_css_has_no_unsubstituted_braces(self):
        # CSS braces and str.format() collide: a leftover field or unbalanced rule
        # here means the whole phantom render raised and the preview came up blank.
        out, _ = self._rows("| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n")
        style = out.split('</style>')[0]
        self.assertNotIn('{}', style)
        self.assertNotIn('{family}', style)
        self.assertEqual(style.count('{'), style.count('}'))
        self.assertGreater(style.count('{'), 1)

    def test_css_font_family_sanitizes_and_falls_back(self):
        self.assertEqual(css_font_family('Maple Mono'), '"Maple Mono", monospace')
        self.assertEqual(css_font_family(None), 'monospace')
        self.assertEqual(css_font_family(''), 'monospace')
        evil = css_font_family('x"; background:url(y)')
        self.assertNotIn(';', evil)
        self.assertNotIn('"x', evil[1:])


class TestListIndentation(unittest.TestCase):
    """Test the re-indentation that lets Python-Markdown nest lists."""

    def test_three_space_sublist_becomes_four(self):
        md = "1. one\n2. two\n   - sub a\n   - sub b\n"
        self.assertEqual(
            normalize_list_indentation(md),
            "1. one\n2. two\n    - sub a\n    - sub b\n",
        )

    def test_two_space_sublists_gain_one_level_per_step(self):
        md = "- a\n  - b\n    - c\n"
        self.assertEqual(
            normalize_list_indentation(md),
            "- a\n    - b\n        - c\n",
        )

    def test_already_four_space_lists_are_untouched(self):
        md = "1. one\n    - sub\n      continued\n2. two\n"
        self.assertEqual(normalize_list_indentation(md), md)

    def test_continuation_lines_follow_their_item(self):
        md = "4. head\n   - item wrapped\n     tail line\n"
        self.assertEqual(
            normalize_list_indentation(md),
            "4. head\n    - item wrapped\n      tail line\n",
        )

    def test_siblings_return_to_their_level(self):
        md = "- a\n  - b\n- c\n"
        self.assertEqual(
            normalize_list_indentation(md),
            "- a\n    - b\n- c\n",
        )

    def test_fenced_code_and_blockquotes_are_left_alone(self):
        md = (
            "```bash\n"
            "# not a marker\n"
            "```\n"
            "> quote\n"
            "> - nested in quote\n"
        )
        self.assertEqual(normalize_list_indentation(md), md)

    def test_marker_looking_lines_inside_indented_fences_are_safe(self):
        md = "- item\n  ```python\n  1. not a list\n  ```\n"
        self.assertEqual(normalize_list_indentation(md), md)

    def test_indented_code_block_outside_lists_is_preserved(self):
        md = "paragraph\n\n    code line\n    more code\n"
        self.assertEqual(normalize_list_indentation(md), md)


class TestOrderedListRendering(unittest.TestCase):
    """Test the minihtml rewrite of ordered and nested lists."""

    def test_ordered_list_gets_literal_markers(self):
        html = "<ol><li>one</li><li>two</li></ol>"
        out = render_ordered_lists(html)
        self.assertNotIn("<ol", out)
        self.assertIn(">1.<", out)
        self.assertIn(">2.<", out)
        self.assertEqual(out.count('class="md-li"'), 2)

    def test_start_and_type_attributes_are_honored(self):
        out = render_ordered_lists('<ol start="7"><li>seven</li></ol>')
        self.assertIn(">7.<", out)
        out = render_ordered_lists('<ol type="a"><li>first</li><li>second</li></ol>')
        self.assertIn(">a.<", out)
        self.assertIn(">b.<", out)
        out = render_ordered_lists('<ol type="I"><li>one</li><li>two</li></ol>')
        self.assertIn(">I.<", out)
        self.assertIn(">II.<", out)

    def test_leading_paragraph_is_lifted_into_the_marker_line(self):
        out = render_ordered_lists("<ol><li><p>text</p><ul><li>sub</li></ul></li></ol>")
        self.assertIn(
            '<span class="md-mk" style="position:relative;left:-1.79em">1.</span>text',
            out,
        )
        self.assertIn('class="md-ul md-ul-2"', out)

    def test_nested_unordered_lists_are_levelled(self):
        out = render_ordered_lists("<ul><li>a<ul><li>b<ul><li>c</li></ul></li></ul></li></ul>")
        self.assertIn('class="md-ul md-ul-1"', out)
        self.assertIn('class="md-ul md-ul-2"', out)
        self.assertIn('class="md-ul md-ul-3"', out)
        self.assertIn('class="md-li-2"', out)

    def test_non_list_markup_and_escaped_tags_pass_through(self):
        html = '<p>not &lt;ol&gt; a list</p><pre><code>x</code></pre>'
        self.assertEqual(render_ordered_lists(html), html)

    def test_inline_style_padding_matches_marker_width(self):
        out = render_ordered_lists(
            "<ol>{}</ol>".format("".join("<li>i</li>" for i in range(12)))
        )
        self.assertIn(">12.<", out)
        self.assertIn('padding-left:2.41em', out)


class TestRenderSettings(unittest.TestCase):
    """Test the front matter that pins mdpopups' extension set."""

    def test_nl2br_is_dropped_by_default(self):
        out = apply_render_settings("# t\n\nbody\n")
        self.assertIn("markdown_extensions:", out)
        self.assertNotIn("nl2br", out)
        self.assertIn("markdown.extensions.admonition", out)
        self.assertTrue(out.endswith("# t\n\nbody\n"))

    def test_hard_line_breaks_keeps_nl2br(self):
        out = apply_render_settings("body\n", hard_line_breaks=True)
        self.assertIn("markdown.extensions.nl2br", out)

    def test_allow_code_wrap_toggle(self):
        self.assertIn("allow_code_wrap: true", apply_render_settings("body\n"))
        self.assertIn(
            "allow_code_wrap: false",
            apply_render_settings("body\n", wrap_code_blocks=False),
        )

    def test_author_declared_keys_win(self):
        md = "---\nmarkdown_extensions:\n- toc\nallow_code_wrap: false\n---\n\nbody\n"
        self.assertEqual(apply_render_settings(md), md)

    def test_existing_front_matter_is_merged(self):
        md = "---\ntitle: Report\n---\n\nbody\n"
        out = apply_render_settings(md)
        self.assertIn("title: Report", out)
        self.assertIn("markdown_extensions:", out)
        self.assertEqual(out.count("---"), 2)

    def test_leading_thematic_break_is_not_treated_as_front_matter(self):
        md = "---\nPlain opening text\n---\n\nbody\n"
        out = apply_render_settings(md)
        self.assertIn("\n---\nPlain opening text\n---\n\nbody\n", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
