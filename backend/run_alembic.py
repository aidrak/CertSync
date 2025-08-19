import os

import alembic.config


def run_alembic():
    # alembic_cfg = ...  # removed unused variable
    alembic.config.main(
        argv=[
            "--raiseerr",
            "revision",
            "--autogenerate",
            "-m",
            "Rename port to management_port",
        ]
    )


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    run_alembic()
