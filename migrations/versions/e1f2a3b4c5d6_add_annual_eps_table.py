"""add_annual_eps_table

Adds the annual_eps table to store per-year diluted EPS values per company.

Revision ID: e1f2a3b4c5d6
Revises: d3e4f5a6b7c8
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'annual_eps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'year', name='uq_annual_eps_company_year'),
    )
    op.create_index('ix_annual_eps_company_id', 'annual_eps', ['company_id'])


def downgrade():
    op.drop_index('ix_annual_eps_company_id', table_name='annual_eps')
    op.drop_table('annual_eps')
