#!/usr/bin/env python3
import os
import argparse
import tiktoken
import yaml
import re
from openai import OpenAI, RateLimitError
from tenacity import retry, stop_after_delay, wait_random_exponential, retry_if_exception_type

# Default settings (can be overridden via CLI
DEFAULT_MODEL_NAME = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0                 # Deterministic output
MAX_TOKENS_PER_CHUNK = 1000             # Lower values can improve translation quality

# System prompt template with a placeholder for the target language.
SYSTEM_PROMPT_TEMPLATE = (
    "You are a professional game translator specializing in Victoria 3 localization.  "
    "Translate a 19th-century strategy game with historical context using formal language while avoiding modern expressions.  "
    "Ensure consistency with existing localization and keep proper names and historical terms unchanged if no proper {target_lang} equivalent exists.  "
    "Do not translate common gaming terms such as 'multiplayer'; leave them as-is if they are widely recognized in {target_lang}.  "
    "Preserve the original meaning, tone, and natural game context, and avoid literal translations that sound unnatural.  "
    "If unsure, leave a valid YAML comment for the reviewer and match the character's gender in pronunciation if needed.  "
    "Keep in mind this is a part of a YAML file; keep it valid and don't forget to escape special characters such as double quotes.  "
    "Translate the YAML content from English to {target_lang}, preserving all keys, numbers, punctuation, and formatting exactly as they are.  "
    "Only translate the human-readable text inside the quotes without adding any extra explanation.  "
    "Do not wrap the text in ```yaml or add any extra characters."
)

# Set the OpenAI API key from environment variable.
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Please set the OPENAI_API_KEY environment variable.")
    exit(1)

client = OpenAI(api_key=api_key)


def chunk_text_by_lines(text: str, max_tokens: int, encoding) -> list[str]:
    """
    Splits the text (by line) into chunks so that each chunk has at most max_tokens tokens.
    """
    lines = text.splitlines(keepends=True)
    chunks = []
    current_chunk = ""
    for line in lines:
        # Count tokens if we add this line to the current chunk.
        current_tokens = len(encoding.encode(current_chunk))
        line_tokens = len(encoding.encode(line))
        if current_tokens + line_tokens > max_tokens and current_chunk:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += line
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


@retry(
    retry=retry_if_exception_type(RateLimitError),
    stop=stop_after_delay(60),
    wait=wait_random_exponential(min=5, max=60)
)
def translate_chunk(chunk: str, system_prompt: str) -> str:
    """
    Calls the OpenAI API to translate a chunk of YAML content.
    Automatically retries on RateLimitError.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Translate the following YAML content from English to the target language:\n\n{chunk}"}
    ]
    response = client.chat.completions.create(
        model=DEFAULT_MODEL_NAME,
        messages=messages,
        temperature=DEFAULT_TEMPERATURE,
    )
    return response.choices[0].message.content.strip()


def translate_file(filepath: str, encoding, target_lang: str, system_prompt: str) -> str:
    """
    Reads a file, splits its content into manageable chunks, translates each chunk,
    and returns the full translated content reindented so that:
      - Empty lines and comment lines (starting with '#') are unchanged.
      - The first non-empty, non-comment header line (e.g. "l_targetlang:") is kept as-is.
      - All subsequent non-empty, non-comment lines are indented with exactly 2 spaces.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    # Replace the header "l_english:" with the target language header.
    target_header = f"l_{target_lang}:"
    text = re.sub(r"l_english:", target_header, text)

    chunks = chunk_text_by_lines(text, MAX_TOKENS_PER_CHUNK, encoding)
    translated_chunks = []
    for i, chunk in enumerate(chunks, start=1):
        print(f"  Translating chunk {i}/{len(chunks)} (approx {len(encoding.encode(chunk))} tokens)...")
        translated = translate_chunk(chunk, system_prompt)
        # Remove surrounding ```yaml tags if present.
        if translated.startswith("```yaml") and translated.endswith("```"):
            translated = translated[7:-3].strip()
        translated_chunks.append(translated)
    final_text = "\n".join(translated_chunks)

    # Reindent the file:
    lines = final_text.splitlines()
    output_lines = []
    header_found = False
    header_pattern = re.compile(r"l_[^:]+:")

    for line in lines:
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            output_lines.append(line)
        elif not header_found and header_pattern.match(stripped):
            # Preserve the first header line as-is.
            output_lines.append(line.strip())
            header_found = True
        else:
            output_lines.append("  " + line.lstrip())
    return "\n".join(output_lines)


def ensure_output_path(input_path: str, input_root: str, output_root: str, target_lang: str) -> str:
    """
    Computes the corresponding output file path under output_root for a given input file.
    If there is '/english' in the path, it is replaced with '/{target_lang}'.
    """
    rel_dir = os.path.relpath(os.path.dirname(input_path), input_root)
    out_dir = os.path.join(output_root, rel_dir)
    out_dir = out_dir.replace("/english", f"/{target_lang}")
    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.basename(input_path).replace("l_english", f"l_{target_lang}")
    return os.path.join(out_dir, filename)


def validate_yaml(file_path: str):
    """
    Checks if the YAML file at file_path is valid.
    If not, prints an error message.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
    except Exception as e:
        print(f"Error: The file '{file_path}' is not a valid YAML file: {e}")


def main():
    global DEFAULT_MODEL_NAME, DEFAULT_TEMPERATURE  # Declare globals at the very beginning.
    parser = argparse.ArgumentParser(
        description="Translate Victoria 3 localization files to a target language."
    )
    parser.add_argument(
        "--input-game-dir",
        required=True,
        help="Input game directory containing the original localization files. This directory should be the 'game/' directory within the game installation."
    )
    parser.add_argument(
        "--language",
        required=True,
        help="Target language code (e.g., czech, polish)"
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for the translated localization files"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_NAME,
        help="OpenAI model to use (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Translation temperature (default: 0)"
    )
    args = parser.parse_args()

    input_root = args.input_game_dir
    output_root = args.output_dir
    target_lang = args.language.lower()

    # Update global model and temperature.
    DEFAULT_MODEL_NAME = args.model
    DEFAULT_TEMPERATURE = args.temperature

    # Prepare the system prompt with the target language.
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(target_lang=target_lang)

    encoding = tiktoken.encoding_for_model(DEFAULT_MODEL_NAME)

    # Walk through only files in the "localization" directory inside the game directory.
    localization_dir = os.path.join(input_root, "localization")
    for root, dirs, files in os.walk(localization_dir):
        for file in files:
            if file.endswith(("_english.yml", "_english.yaml")):
                input_file_path = os.path.join(root, file)
                print(f"\nTranslating file: {input_file_path}")
                translated_text = translate_file(input_file_path, encoding, target_lang, system_prompt)
                output_file_path = ensure_output_path(input_file_path, input_root, output_root, target_lang)
                with open(output_file_path, 'w', encoding='utf-8') as out_f:
                    out_f.write(translated_text)
                # Optionally, call an external script to add BOM (if needed)
                os.system(f"python3 add_bom.py {output_file_path}")
                print(f"Saved translated file to: {output_file_path}")
                validate_yaml(output_file_path)


if __name__ == "__main__":
    main()
