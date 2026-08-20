"""python -m openmontage.mcp → help."""

from __future__ import annotations


def main() -> None:
    print(
        "OpenMontage MCP\n"
        "  python -m openmontage.mcp.bootstrap       # BootStrap facade (setup + minimal produce)\n"
        "  python -m openmontage.mcp.doctor          # P0/P1 diagnosis + sandbox project API\n"
        "  python -m openmontage.mcp.media           # P1 zero-key media tools (stdio)\n"
        "  python -m openmontage.mcp.providers_tts   # P2 advanced/paid TTS (stdio)\n"
    )


if __name__ == "__main__":
    main()
