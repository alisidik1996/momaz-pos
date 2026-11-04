def safe_csv_cell(value):
    """Keep untrusted spreadsheet text from being interpreted as a formula."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value
