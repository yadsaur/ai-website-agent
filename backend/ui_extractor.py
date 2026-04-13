from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class UIFact:
    element_type: str
    label: str
    location: str
    href: Optional[str]
    extra: str = ""


@dataclass
class UIStructure:
    page_url: str
    page_title: str
    facts: list[UIFact] = field(default_factory=list)


def extract_ui_structure(html: str, page_url: str, page_title: str) -> UIStructure:
    soup = BeautifulSoup(html, "lxml")
    structure = UIStructure(page_url=page_url, page_title=page_title)
    root_path = re.sub(r"^(https?://[^/]+).*$", r"\1", page_url).rstrip("/")
    site_name_hint = (page_title.split("|", 1)[0].split("—", 1)[0].strip() if page_title else "").lower()

    def get_label(el) -> str:
        for attr in ["aria-label", "title", "alt", "placeholder"]:
            value = el.get(attr, "").strip()
            if value:
                return value
        text = el.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text[:80] if text else ""

    def infer_position(el) -> str:
        position_map = [
            (
                ["sticky-header", "top-bar", "topbar", "top-nav", "header-nav", "site-header", "page-header", "masthead"],
                "sticky header bar at the top",
            ),
            (
                ["navbar", "nav-bar", "main-nav", "primary-nav", "navigation", "menu-bar", "menubar"],
                "top navigation bar",
            ),
            (
                ["sidebar", "side-bar", "side-panel", "left-sidebar", "right-sidebar", "aside"],
                "sidebar panel",
            ),
            (
                ["footer", "site-footer", "page-footer", "bottom-bar"],
                "footer at the bottom",
            ),
            (
                ["hero", "banner", "jumbotron", "masthead", "intro"],
                "hero/banner section",
            ),
            (["breadcrumb", "breadcrumbs"], "breadcrumb trail"),
            (["modal", "dialog", "popup", "overlay"], "popup/modal dialog"),
            (
                ["search", "search-bar", "searchbar", "search-form", "search-box", "searchbox"],
                "search area",
            ),
            (["cta", "call-to-action", "action-bar"], "call-to-action section"),
            (["toolbar", "tool-bar", "action-toolbar"], "toolbar"),
        ]
        tag_map = {
            "header": "header area at the top of the page",
            "nav": "navigation menu",
            "footer": "footer at the bottom of the page",
            "aside": "sidebar panel",
            "main": "main content area",
        }

        chain = [el] + list(el.parents)
        for ancestor in chain:
            if not getattr(ancestor, "get", None):
                continue
            tag = ancestor.name or ""
            if tag in tag_map:
                return tag_map[tag]
            classes = " ".join(ancestor.get("class", [])).lower()
            ancestor_id = (ancestor.get("id") or "").lower()
            combined = f"{classes} {ancestor_id}"
            for terms, label in position_map:
                if any(term in combined for term in terms):
                    return label
        return "page body"

    nav_containers = soup.find_all(["nav", "header"]) + soup.find_all(attrs={"role": "navigation"})
    seen_nav_labels = set()
    for container in nav_containers:
        position = infer_position(container)
        for anchor in container.find_all("a", href=True):
            label = get_label(anchor)
            if not label or label.lower() in seen_nav_labels:
                continue
            seen_nav_labels.add(label.lower())
            structure.facts.append(
                UIFact(
                    element_type="nav_link",
                    label=label,
                    location=position,
                    href=anchor.get("href", ""),
                )
            )

    search_inputs = soup.find_all("input", attrs={"type": lambda value: value in [None, "text", "search"]})
    for input_el in search_inputs:
        class_name = input_el.get("class", [""])[0] if input_el.get("class") else ""
        combined = " ".join(
            [
                input_el.get("type", ""),
                input_el.get("name", ""),
                input_el.get("id", ""),
                class_name,
                input_el.get("placeholder", ""),
                input_el.get("aria-label", ""),
            ]
        ).lower()
        if any(keyword in combined for keyword in ["search", "query", "q", "find", "lookup", "keyword"]):
            position = infer_position(input_el)
            label = get_label(input_el) or "search box"
            structure.facts.append(
                UIFact(
                    element_type="search_input",
                    label=label,
                    location=position,
                    href=None,
                )
            )

    for form in soup.find_all("form"):
        action = (form.get("action") or "").lower()
        role = (form.get("role") or "").lower()
        classes = " ".join(form.get("class", [])).lower()
        if "search" in action or "search" in role or "search" in classes:
            position = infer_position(form)
            structure.facts.append(
                UIFact(
                    element_type="search_form",
                    label="search form",
                    location=position,
                    href=None,
                )
            )

    for button in soup.find_all(["button", "a"]):
        label = get_label(button)
        if not label:
            continue
        classes = " ".join(button.get("class", [])).lower()
        role = (button.get("role") or "").lower()
        is_cta = any(
            keyword in classes
            for keyword in [
                "btn",
                "button",
                "cta",
                "action",
                "subscribe",
                "signup",
                "register",
                "login",
                "signin",
                "download",
                "buy",
                "start",
            ]
        ) or role == "button"
        label_lower = label.lower()
        is_cta_text = any(
            keyword in label_lower
            for keyword in [
                "sign up",
                "subscribe",
                "get started",
                "try free",
                "buy",
                "download",
                "register",
                "log in",
                "login",
                "join",
                "start free",
            ]
        )
        if is_cta or is_cta_text:
            position = infer_position(button)
            structure.facts.append(
                UIFact(
                    element_type="cta_button",
                    label=label,
                    location=position,
                    href=button.get("href", "") if button.name == "a" else "",
                )
            )

    for element in soup.find_all(["a", "img"]):
        classes = " ".join(element.get("class", [])).lower()
        element_id = (element.get("id") or "").lower()
        alt = (element.get("alt") or "").lower()
        if "logo" in classes or "logo" in element_id or "logo" in alt:
            label = get_label(element) or "site logo"
            position = infer_position(element)
            structure.facts.append(
                UIFact(
                    element_type="logo",
                    label=label,
                    location=position,
                    href=element.get("href", "") if element.name == "a" else "",
                )
            )
            break
    else:
        for anchor in soup.find_all("a", href=True):
            href = (anchor.get("href") or "").strip()
            label = get_label(anchor)
            if not label:
                continue
            normalized_href = href.rstrip("/")
            label_lower = label.lower()
            classes = " ".join(anchor.get("class", [])).lower()
            element_id = (anchor.get("id") or "").lower()
            if (
                normalized_href in {"", "/", root_path}
                and infer_position(anchor) in {"header area at the top of the page", "navigation menu", "top navigation bar", "sticky header bar at the top"}
                and (
                    site_name_hint and site_name_hint in label_lower
                    or any(term in f"{classes} {element_id}" for term in ["brand", "site-title", "wordmark", "home"])
                )
            ):
                structure.facts.append(
                    UIFact(
                        element_type="logo",
                        label=label,
                        location=infer_position(anchor),
                        href=href,
                    )
                )
                break

    footer = soup.find("footer")
    if not footer:
        footer = soup.find(attrs={"class": lambda classes: classes and "footer" in " ".join(classes).lower()})
    if footer:
        for anchor in footer.find_all("a", href=True):
            label = get_label(anchor)
            if label:
                structure.facts.append(
                    UIFact(
                        element_type="footer_link",
                        label=label,
                        location="footer at the bottom of the page",
                        href=anchor.get("href", ""),
                    )
                )

    dropdown_containers = soup.find_all(
        attrs={
            "class": lambda classes: classes
            and any(keyword in " ".join(classes).lower() for keyword in ["dropdown", "submenu", "mega-menu", "flyout"])
        }
    )
    for dropdown in dropdown_containers[:5]:
        parent_link = dropdown.find_previous("a")
        parent_label = get_label(parent_link) if parent_link else "menu"
        position = infer_position(dropdown)
        sub_links = [get_label(anchor) for anchor in dropdown.find_all("a") if get_label(anchor)][:8]
        if sub_links:
            structure.facts.append(
                UIFact(
                    element_type="dropdown_menu",
                    label=parent_label,
                    location=position,
                    href=None,
                    extra=f"contains: {', '.join(sub_links)}",
                )
            )

    seen = set()
    deduped = []
    for fact in structure.facts:
        key = (fact.element_type, fact.label.lower()[:40])
        if key not in seen:
            seen.add(key)
            deduped.append(fact)
    structure.facts = deduped
    return structure


def ui_structure_to_text(structure: UIStructure) -> str:
    if not structure.facts:
        logger.debug("No UI facts found for %s", structure.page_url)
        return ""

    lines = [f"UI Layout and Navigation Guide for: {structure.page_title}", f"Page: {structure.page_url}", ""]

    groups: dict[str, list[UIFact]] = {}
    for fact in structure.facts:
        groups.setdefault(fact.element_type, []).append(fact)

    if "search_input" in groups or "search_form" in groups:
        lines.append("Search")
        for fact in groups.get("search_input", []) + groups.get("search_form", []):
            lines.append(
                f'The search bar ("{fact.label}") is located in the {fact.location}. '
                f"To search for content, look for the search input in the {fact.location}."
            )
        lines.append("")

    if "nav_link" in groups:
        lines.append("Navigation Menu")
        by_location: dict[str, list[str]] = {}
        for fact in groups["nav_link"]:
            by_location.setdefault(fact.location, []).append(fact.label)
        for location, labels in by_location.items():
            lines.append(f'The {location} contains the following navigation links: {", ".join(labels)}.')
            for label in labels:
                lines.append(f'The "{label}" link is in the {location}.')
        lines.append("")

    if "cta_button" in groups:
        lines.append("Buttons and Actions")
        for fact in groups["cta_button"]:
            line = f'The "{fact.label}" button is located in the {fact.location}.'
            if fact.href:
                line += f" It links to: {fact.href}."
            lines.append(line)
        lines.append("")

    if "dropdown_menu" in groups:
        lines.append("Dropdown Menus")
        for fact in groups["dropdown_menu"]:
            lines.append(f'The "{fact.label}" menu in the {fact.location} is a dropdown and {fact.extra}.')
        lines.append("")

    if "logo" in groups:
        for fact in groups["logo"]:
            line = f'The site logo ("{fact.label}") is in the {fact.location}.'
            if fact.href:
                line += f" Clicking it goes to: {fact.href}."
            lines.append(line)

    if "footer_link" in groups:
        lines.append("Footer Links")
        footer_labels = [fact.label for fact in groups["footer_link"]]
        if footer_labels:
            lines.append(f'The footer at the bottom of the page contains links to: {", ".join(footer_labels[:20])}.')
        lines.append("")

    text = "\n".join(lines)
    logger.debug("Built %s UI facts for %s", len(structure.facts), structure.page_url)
    return text
