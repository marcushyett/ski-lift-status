"""
Nuxt.js payload extractor adapter.

This adapter extracts lift/trail data from Nuxt.js applications by parsing
the __NUXT__ hydration payload which contains server-side rendered data.

Used for resorts like:
- Cervinia (cervinia.it)
"""

import re
import json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from ..models import CapturedResource

logger = structlog.get_logger(__name__)


@dataclass
class NuxtLift:
    """Lift data extracted from Nuxt.js payload."""
    name: str
    status: str | None
    lift_type: str | None
    message: str | None = None
    wait_time: str | None = None
    sector: str | None = None
    # Additional fields
    opening_time: str | None = None
    closing_time: str | None = None


@dataclass
class NuxtTrail:
    """Trail data extracted from Nuxt.js payload."""
    name: str
    status: str | None
    difficulty: str | None
    sector: str | None = None
    # Additional fields
    opening_time: str | None = None
    closing_time: str | None = None


@dataclass
class NuxtData:
    """Combined lift and trail data from Nuxt.js payload."""
    lifts: list[NuxtLift]
    trails: list[NuxtTrail]


# Cervinia-specific status mappings
CERVINIA_STATUS_MAP = {
    "O": "open",        # Ouvert
    "P": "forecast",    # Prévision
    "F": "closed",      # Fermé
    "H": "maintenance", # Hors service
}

# Cervinia-specific type mappings
CERVINIA_TYPE_MAP = {
    "TC": "gondola",          # Télécabine
    "TPH": "cable_car",       # Téléphérique
    "TS": "chairlift",        # Télésiège
    "TK": "t_bar",            # Téléski
    "TAP": "magic_carpet",    # Tapis roulant
}

# Difficulty mappings
CERVINIA_DIFFICULTY_MAP = {
    "V": "easy",        # Verte
    "B": "intermediate", # Bleue
    "R": "advanced",    # Rouge
    "N": "expert",      # Noire
    # Handle quoted variants
    '"V"': "easy",
    '"B"': "intermediate",
    '"R"': "advanced",
    '"N"': "expert",
}


def detect_nuxtjs(resources: list[CapturedResource]) -> bool:
    """Check if the captured resources indicate a Nuxt.js application.

    Args:
        resources: List of captured network resources

    Returns:
        True if Nuxt.js is detected
    """
    for resource in resources:
        content = resource.content or ""
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")

        if "__NUXT__" in content or "window.__NUXT__" in content:
            return True

    return False


def extract_nuxt_iife_payload(html: str) -> dict[str, Any] | None:
    """Extract and evaluate a Nuxt.js IIFE payload.

    Nuxt.js uses an IIFE (Immediately Invoked Function Expression) with
    compressed variable names for the payload. This function extracts the
    parameter values and reconstructs the JSON.

    Args:
        html: The HTML content containing __NUXT__

    Returns:
        Parsed payload dict or None if extraction fails
    """
    log = logger.bind(adapter="nuxtjs")

    # Find the __NUXT__ IIFE pattern:
    # __NUXT__ = (function(a,b,c,...) { return {...} })(val1,val2,val3,...)
    iife_pattern = r'__NUXT__\s*=\s*\(function\(([^)]+)\)\s*\{return\s*(\{.*?\})\}\)\(([^)]+)\)'

    match = re.search(iife_pattern, html, re.DOTALL)
    if not match:
        log.debug("no_iife_pattern_found")
        return None

    param_names = match.group(1)  # a,b,c,...
    json_template = match.group(2)  # The JSON-like object with variable refs
    param_values = match.group(3)  # The actual values

    # Parse parameter names
    params = [p.strip() for p in param_names.split(",")]

    # Parse parameter values - this is tricky due to nested structures
    # The values are a mix of: strings, numbers, null, and variable refs
    values = _parse_iife_values(param_values)

    if len(params) != len(values):
        log.warning(
            "param_value_mismatch",
            params_count=len(params),
            values_count=len(values),
        )
        # Try to continue anyway

    # Create substitution map
    sub_map = {}
    for i, param in enumerate(params):
        if i < len(values):
            sub_map[param] = values[i]

    # Substitute variables in JSON template
    result_json = _substitute_variables(json_template, sub_map)

    try:
        # Try to parse the resulting JSON
        return json.loads(result_json)
    except json.JSONDecodeError as e:
        log.debug("json_parse_failed", error=str(e))
        return None


def _parse_iife_values(values_str: str) -> list[Any]:
    """Parse the comma-separated values from a Nuxt IIFE.

    Values can be:
    - Quoted strings: "hello", 'world'
    - Numbers: 123, -45.6
    - null, true, false, void 0
    - Variable references (to earlier params): a, b, c

    Args:
        values_str: The comma-separated values string

    Returns:
        List of parsed values
    """
    values = []
    current = ""
    in_string = False
    string_char = None
    depth = 0  # For nested structures

    i = 0
    while i < len(values_str):
        char = values_str[i]

        if in_string:
            current += char
            if char == string_char and (i == 0 or values_str[i - 1] != "\\"):
                in_string = False
        elif char in "\"'":
            in_string = True
            string_char = char
            current += char
        elif char in "([{":
            depth += 1
            current += char
        elif char in ")]}":
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            # End of value
            value = _parse_single_value(current.strip())
            values.append(value)
            current = ""
        else:
            current += char

        i += 1

    # Don't forget the last value
    if current.strip():
        value = _parse_single_value(current.strip())
        values.append(value)

    return values


def _parse_single_value(value_str: str) -> Any:
    """Parse a single value from the IIFE parameters.

    Args:
        value_str: A single value string

    Returns:
        The parsed value
    """
    value_str = value_str.strip()

    # Handle special keywords
    if value_str in ("null", "void 0"):
        return None
    if value_str == "true":
        return True
    if value_str == "false":
        return False

    # Handle quoted strings
    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        # Unescape the string
        inner = value_str[1:-1]
        inner = inner.replace("\\/", "/")
        inner = inner.replace("\\n", "\n")
        inner = inner.replace("\\t", "\t")
        inner = inner.replace('\\"', '"')
        inner = inner.replace("\\'", "'")
        return inner

    # Handle numbers
    try:
        if "." in value_str:
            return float(value_str)
        return int(value_str)
    except ValueError:
        pass

    # Otherwise, it's a variable reference - return as string placeholder
    return f"__VAR__{value_str}__"


def _substitute_variables(json_template: str, sub_map: dict[str, Any]) -> str:
    """Substitute variable references in the JSON template.

    Args:
        json_template: JSON template with variable references
        sub_map: Map of variable name to value

    Returns:
        JSON string with variables substituted
    """
    result = json_template

    # Sort by length (longest first) to avoid partial matches
    sorted_vars = sorted(sub_map.keys(), key=len, reverse=True)

    for var_name in sorted_vars:
        value = sub_map[var_name]

        # Convert value to JSON-safe string
        if value is None:
            replacement = "null"
        elif isinstance(value, bool):
            replacement = "true" if value else "false"
        elif isinstance(value, str):
            # Need to re-escape for JSON
            replacement = json.dumps(value)
        elif isinstance(value, (int, float)):
            replacement = str(value)
        else:
            replacement = json.dumps(value)

        # Replace variable references
        # Variable names appear as bare identifiers in JSON property values
        # We need to be careful to only replace whole words
        pattern = rf'(?<=[:\[,\s])({re.escape(var_name)})(?=[,\]\}}\s:])'
        result = re.sub(pattern, replacement, result)

    return result


def extract_cervinia(html: str) -> NuxtData | None:
    """Extract lift/trail data from Cervinia.it HTML.

    Cervinia uses a Nuxt.js application with a compressed IIFE payload.
    The lift data is in: optionsAPI.impianti.impianti_da_xml.SECTEUR[].REMONTEE[]
    The trail data is in: optionsAPI.impianti.impianti_da_xml.SECTEUR[].PISTE[]

    Args:
        html: The HTML content from cervinia.it/en/impianti

    Returns:
        NuxtData with lifts and trails, or None if extraction fails
    """
    log = logger.bind(adapter="nuxtjs", resort="cervinia")

    lifts: list[NuxtLift] = []
    trails: list[NuxtTrail] = []

    # For Cervinia, the data is embedded but compressed
    # We'll use regex to extract the structured data patterns directly

    # Find SECTEUR data with REMONTEE (lifts) and PISTE (trails)
    # Pattern: SECTEUR:[{...}]
    secteur_pattern = r'SECTEUR:\[(\{.*?\})\]'
    secteur_matches = re.findall(secteur_pattern, html, re.DOTALL)

    if not secteur_matches:
        log.warning("no_secteur_data_found")

    # Also try to find the timing data
    timing_pattern = r'orari_impianti_singoli:\[([^\]]+)\]'
    timing_match = re.search(timing_pattern, html)

    if timing_match:
        # Parse timing entries (currently just for logging)
        timing_entries = re.findall(
            r'\{nome:([^,]+),orario_apertura:([^,]+),orario_chiusura:([^}]+)\}',
            timing_match.group(1)
        )
        log.debug("found_timing_entries", count=len(timing_entries))

    # Extract REMONTEE (lifts) patterns directly
    lift_pattern = r'REMONTEE:\[(.*?)\]'
    lift_sections = re.findall(lift_pattern, html, re.DOTALL)

    for section in lift_sections:
        # Find individual lift entries
        entry_pattern = r'\{"@attributes":\{nom:([^,]+),etat:([^,]+),type:([^,]+),msg:([^,]+),attente:([^}]+)\}\}'
        entries = re.findall(entry_pattern, section)

        for entry in entries:
            nom_var, etat_var, type_var, msg_var, attente_var = entry

            # The values are variable references, we need to resolve them
            # For now, just use the variable name as a placeholder
            lifts.append(NuxtLift(
                name=nom_var,  # Will be resolved later
                status=etat_var,
                lift_type=type_var,
                message=msg_var if msg_var != "a" else None,
                wait_time=attente_var if attente_var != "c" else None,
            ))

    # Extract PISTE (trails) patterns
    trail_pattern = r'PISTE:\[(.*?)\]'
    trail_sections = re.findall(trail_pattern, html, re.DOTALL)

    for section in trail_sections:
        entry_pattern = r'\{"@attributes":\{nom:([^,]+),etat:([^,]+),type:([^,}]+)'
        entries = re.findall(entry_pattern, section)

        for entry in entries:
            nom_var, etat_var, type_var = entry

            trails.append(NuxtTrail(
                name=nom_var,
                status=etat_var,
                difficulty=type_var,
            ))

    log.info(
        "extraction_complete",
        lift_count=len(lifts),
        trail_count=len(trails),
    )

    return NuxtData(lifts=lifts, trails=trails)


def _extract_cervinia_var_map(html: str) -> dict[str, Any]:
    """Extract variable mapping from Cervinia IIFE.

    The Nuxt payload uses an IIFE with compressed variable names:
    __NUXT__ = (function(a,b,c,...){return {body}})(val1,val2,val3,...)

    Args:
        html: HTML content

    Returns:
        Dict mapping variable names to values
    """
    log = logger.bind(adapter="nuxtjs", resort="cervinia")

    # Find the IIFE structure
    pattern = r'__NUXT__\s*=\s*\(function\(([^)]+)\)\{return\s*\{.*?\}\}\('
    match = re.search(pattern, html, re.DOTALL)

    if not match:
        log.warning("no_iife_pattern_found")
        return {}

    # Extract parameter names
    params = [p.strip() for p in match.group(1).split(",")]
    log.debug("found_params", count=len(params))

    # Find values - everything between }( and ));
    end_idx = html.find("));", match.end())
    if end_idx == -1:
        log.warning("no_values_end_found")
        return {}

    values_str = html[match.end():end_idx]

    # Parse values
    values = []
    current = ""
    in_string = False
    string_char = None

    for i, c in enumerate(values_str):
        if in_string:
            current += c
            if c == string_char and (i == 0 or values_str[i - 1] != "\\"):
                in_string = False
        elif c == '"':
            in_string = True
            string_char = c
            current += c
        elif c == "," and not in_string:
            values.append(current.strip())
            current = ""
        else:
            current += c

    if current.strip():
        values.append(current.strip())

    log.debug("found_values", count=len(values))

    # Create mapping
    var_map: dict[str, Any] = {}
    for i, param in enumerate(params):
        if i < len(values):
            val = values[i]
            # Parse the value
            if val == "true":
                var_map[param] = True
            elif val == "false":
                var_map[param] = False
            elif val.startswith('"') and val.endswith('"'):
                # Unescape string
                inner = val[1:-1]
                inner = inner.replace("\\u002F", "/")
                inner = inner.replace("\\n", "\n")
                var_map[param] = inner
            else:
                try:
                    var_map[param] = int(val)
                except ValueError:
                    var_map[param] = val

    return var_map


async def fetch_cervinia() -> NuxtData | None:
    """Fetch and extract lift/trail data from Cervinia.it.

    Returns:
        NuxtData with lifts and trails, or None if fetch fails
    """
    log = logger.bind(adapter="nuxtjs", resort="cervinia")

    url = "https://www.cervinia.it/en/impianti"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            log.debug("fetching_page", url=url)
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text

    except httpx.HTTPError as e:
        log.error("http_error", error=str(e))
        return None

    # Extract variable mapping
    var_map = _extract_cervinia_var_map(html)
    if not var_map:
        log.warning("no_var_map_extracted")
        return extract_cervinia(html)

    log.debug("var_map_created", var_count=len(var_map))

    # Now extract lift/trail data with resolved names
    lifts: list[NuxtLift] = []
    trails: list[NuxtTrail] = []

    # Extract REMONTEE (lifts)
    lift_pattern = r'\{"@attributes":\{nom:([^,]+),etat:([^,]+),type:([^,]+),msg:([^,]+),attente:([^}]+)\}\}'
    lift_entries = re.findall(lift_pattern, html)

    for entry in lift_entries:
        nom_var, etat_var, type_var, msg_var, attente_var = entry

        # Resolve variable names
        name = var_map.get(nom_var, nom_var)
        status = var_map.get(etat_var, etat_var)
        lift_type = var_map.get(type_var, type_var)
        msg = var_map.get(msg_var, msg_var)
        wait = var_map.get(attente_var, attente_var)

        # Clean up name (remove quotes if present)
        if isinstance(name, str):
            name = name.strip('"')

        # Map status codes
        status_mapped = CERVINIA_STATUS_MAP.get(status, status) if isinstance(status, str) else status

        # Map lift types
        type_mapped = CERVINIA_TYPE_MAP.get(lift_type, lift_type) if isinstance(lift_type, str) else lift_type

        if isinstance(name, str) and name:
            lifts.append(NuxtLift(
                name=name,
                status=status_mapped,
                lift_type=type_mapped,
                message=msg if msg and msg != "" else None,
                wait_time=str(wait) if wait and wait not in (0, None, "", "0") else None,
            ))

    # Extract PISTE (trails) - note: difficulty is in 'niveau' field
    trail_pattern = r'\{"@attributes":\{nom:([^,]+),etat:([^,]+),type:[^,]+,niveau:([^,]+)'
    trail_entries = re.findall(trail_pattern, html)

    for entry in trail_entries:
        nom_var, etat_var, niveau_var = entry

        name = var_map.get(nom_var, nom_var)
        status = var_map.get(etat_var, etat_var)
        difficulty = var_map.get(niveau_var, niveau_var)

        # Clean up name (remove quotes if present)
        if isinstance(name, str):
            name = name.strip('"')

        # Map status and difficulty
        status_mapped = CERVINIA_STATUS_MAP.get(status, status) if isinstance(status, str) else status
        diff_mapped = CERVINIA_DIFFICULTY_MAP.get(difficulty, difficulty) if isinstance(difficulty, str) else difficulty

        if isinstance(name, str) and name:
            trails.append(NuxtTrail(
                name=name,
                status=status_mapped,
                difficulty=diff_mapped,
            ))

    # Deduplicate by name
    seen_lift_names: set[str] = set()
    unique_lifts = []
    for lift in lifts:
        if lift.name not in seen_lift_names:
            seen_lift_names.add(lift.name)
            unique_lifts.append(lift)

    seen_trail_names: set[str] = set()
    unique_trails = []
    for trail in trails:
        if trail.name not in seen_trail_names:
            seen_trail_names.add(trail.name)
            unique_trails.append(trail)

    log.info(
        "fetch_complete",
        lift_count=len(unique_lifts),
        trail_count=len(unique_trails),
    )

    return NuxtData(lifts=unique_lifts, trails=unique_trails)


def extract(resources: list[CapturedResource]) -> NuxtData | None:
    """Extract lift/run data from captured Nuxt.js resources.

    Args:
        resources: List of captured network resources

    Returns:
        NuxtData if extraction successful, None otherwise
    """
    for resource in resources:
        content = resource.content or ""
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")

        if "__NUXT__" in content:
            # Try to extract from this resource
            if "cervinia.it" in resource.url:
                return extract_cervinia(content)

    return None
