"""remove_user_id_from_companies

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # 1. Data migration: for each ticker, keep only the row with the latest
    #    fetched_at and delete all other duplicates.
    bind.execute(text("""
        DELETE FROM companies
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id
                FROM companies c1
                WHERE fetched_at = (
                    SELECT MAX(fetched_at)
                    FROM companies c2
                    WHERE c2.ticker = c1.ticker
                )
            ) AS keepers
        )
    """))

    with op.batch_alter_table('companies', schema=None) as batch_op:
        # 2. Drop the old (user_id, ticker) unique constraint
        batch_op.drop_constraint('uq_company_user_ticker', type_='unique')
        # 3. Drop the user_id index
        batch_op.drop_index('ix_companies_user_id')
        # 4. Drop the user_id column (FK to users)
        batch_op.drop_column('user_id')
        # 5. Add a unique constraint on ticker alone
        batch_op.create_unique_constraint('uq_company_ticker', ['ticker'])


def downgrade():
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_constraint('uq_company_ticker', type_='unique')
        batch_op.add_column(
            sa.Column('user_id', sa.Integer(), nullable=True)
        )
        batch_op.create_index('ix_companies_user_id', ['user_id'])
        batch_op.create_unique_constraint('uq_company_user_ticker', ['user_id', 'ticker'])
