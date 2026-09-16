"""Compatibility entry point for the spatial-grid paper experiment condition."""

from experiment_server import main


if __name__ == "__main__":
    main(default_condition="spatial", default_port=8760)
