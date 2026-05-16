# altbrow/utils.py
#
#   format_size()


def format_size(size_bytes: int) -> str:
  """Return a human-readable binary size string (IEC units)."""
  if size_bytes >= 1 << 40:
    return f"{size_bytes / (1 << 40):.1f} TiB"
  elif size_bytes >= 1 << 30:
    return f"{size_bytes / (1 << 30):.1f} GiB"
  elif size_bytes >= 1 << 20:
    return f"{size_bytes / (1 << 20):.1f} MiB"
  elif size_bytes >= 1 << 10:
    return f"{size_bytes / (1 << 10):.1f} KiB"
  else:
    return f"{size_bytes} B"
