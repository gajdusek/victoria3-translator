import re
import yaml
from yaml.nodes import MappingNode, ScalarNode


class DoubleQuotedValuesDumper(yaml.SafeDumper):
    """
    A custom dumper that leaves dictionary keys unquoted
    but forces double quotes for string values in YAML.
    """

    def represent_mapping(self, tag, mapping, flow_style=None):
        """
        Overridden to handle each dict key/value. Keys are unquoted,
        values are forcibly quoted if they are strings.
        """
        # Create a new MappingNode for this dictionary
        node = MappingNode(tag, value=[], flow_style=flow_style)

        # Sort if PyYAML wants sorting; we respect sort_keys=False by default
        if self.sort_keys:
            mapping = dict(sorted(mapping.items(), key=lambda x: x[0]))

        # For each key/value in the dictionary...
        for key, val in mapping.items():
            # Represent the key
            node_key = self.represent_data(key)
            # Force no quotes on keys
            if isinstance(node_key, ScalarNode):
                # style=None means no forced quotes
                node_key.style = None

            # Represent the value
            node_val = self.represent_data(val)
            # If it's a scalar string, force double quotes
            if isinstance(node_val, ScalarNode) and node_val.tag == 'tag:yaml.org,2002:str':
                node_val.style = '"'

            # Add the pair to the MappingNode
            node.value.append((node_key, node_val))

        return node


def dump_keys_unquoted_values_quoted(data) -> str:
    """
    Dumps YAML such that:
      - Dictionary keys remain unquoted (if valid unquoted).
      - Dictionary values that are strings are always enclosed in double quotes.
    To match Paradox non-standard YAML files.
    """
    return yaml.dump(
        data,
        Dumper=DoubleQuotedValuesDumper,
        default_flow_style=False,
        sort_keys=False,      # Respect the insertion order
        allow_unicode=True
    )


def validate_yaml(file_path: str):
    """
    Checks if the YAML file at file_path is valid.
    If not, prints an error message.
    FIXME: This does not take into account specifics of Paradox YAML files, so it produces false
    negatives.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
    except Exception as e:
        print(f"Error: The file '{file_path}' is not a valid YAML file: {e}")


def parse_paradox_yaml(filepath: str) -> dict:
    """
    Parses a Paradox-non-stadard YAML files used for localization files (e.g., languages.yml)
    where each block begins with a header line like 'l_english:',
    followed by key-value lines (like ' l_english:1 "English"').
    Returns a dict of dicts, for example:
    {
      "l_english": {
         "l_english:1": "English",
         "l_braz_por:1": "Português do Brasil",
         ...
      },
      "l_braz_por": {
         ...
      },
      ...
    }
    """
    header_regex = re.compile(r"^\s*(l_[A-Za-z0-9_]+):\s*$")
    entry_regex = re.compile(r'^\s+(l_[A-Za-z0-9_]+:\d?)\s+"(.*)"\s*$')

    blocks: dict[str, dict[str, str]] = {}
    current_header = None

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            # Remove BOM if present at line start
            line = line.lstrip('\ufeff').rstrip('\n')

            if not line.strip():
                continue  # skip empty lines

            # Match header lines (allowing leading spaces, removing BOM)
            match_header = header_regex.match(line)
            if match_header:
                current_header = match_header.group(1)
                blocks[current_header] = {}
                continue

            # Match entry lines
            match_entry = entry_regex.match(line)
            if match_entry and current_header is not None:
                key, val = match_entry.groups()
                blocks[current_header][key] = val
            else:
                # Could handle comments or skip lines
                pass

    return blocks
