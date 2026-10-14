"""Private semantic source-block candidate; no evidence or origin inference."""

import re
from html.parser import HTMLParser

from .publication import Publication


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []
        self.publication = Publication()
        self.jsonld_parts = None
        self.jsonld_size = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if (
            not self.hidden
            and tag == "meta"
            and (attributes.get("property") or attributes.get("name") or "").lower()
            in {
                "article:published_time",
                "datepublished",
                "dc.date.issued",
                "dcterms.issued",
                "citation_publication_date",
                "pubdate",
            }
        ):
            self.publication.add(attributes.get("content"))
        if (
            not self.hidden
            and tag == "time"
            and attributes.get("itemprop") == "datePublished"
        ):
            self.publication.add(attributes.get("datetime"))
        if (
            not self.hidden
            and tag == "script"
            and attributes.get("type", "").lower() == "application/ld+json"
        ):
            self.jsonld_parts = []
            self.jsonld_size = 0
        if tag in ("script", "style", "noscript", "template"):
            self.hidden += 1
        if not self.hidden:
            if tag in (
                "p",
                "li",
                "tr",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "blockquote",
                "dt",
                "dd",
            ):
                self.parts.append("\n\n")
            elif tag in ("br", "div", "td", "th"):
                self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "script" and self.jsonld_parts is not None:
            if self.jsonld_size <= 65536:
                self.publication.jsonld("".join(self.jsonld_parts))
            self.jsonld_parts = None
        if tag in ("script", "style", "noscript", "template") and self.hidden:
            self.hidden -= 1
        if not self.hidden:
            if tag in (
                "p",
                "li",
                "tr",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "blockquote",
                "dt",
                "dd",
            ):
                self.parts.append("\n\n")
            elif tag in ("div",):
                self.parts.append("\n")
            else:
                self.parts.append(" ")

    def handle_data(self, text):
        if self.jsonld_parts is not None:
            self.jsonld_size += len(text)
            if self.jsonld_size <= 65536:
                self.jsonld_parts.append(text)
        if not self.hidden:
            # HTML indentation is inline whitespace, not a semantic paragraph.
            self.parts.append(re.sub(r"\s+", " ", text))

    def rendered_text(self):
        blocks = []
        for block in "".join(self.parts).split("\n\n"):
            lines = [
                " ".join(line.split()) for line in block.splitlines() if line.strip()
            ]
            if lines:
                blocks.append("\n".join(lines))
        return "\n\n".join(blocks)
