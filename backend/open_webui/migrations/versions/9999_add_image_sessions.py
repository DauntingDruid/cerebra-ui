"""add image_sessions table for multi-round generation

Revision ID: 9999_image_sessions
Revises: 3781e22d8b01
Create Date: 2025-10-19
"""

from alembic import op
import sqlalchemy as sa
from typing import Union

# revision identifiers, used by Alembic.
revision: str = "9999_image_sessions"
down_revision: Union[str, None] = "3781e22d8b01"  # ✅ 修正为实际的 head
branch_labels = None
depends_on = None

def upgrade():
    """Create image_sessions table"""
    op.create_table(
        'image_sessions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('chat_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.Column('parent_session_id', sa.String(), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('optimized_prompt', sa.Text(), nullable=True),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('fal_seed', sa.BigInteger(), nullable=True),
        sa.Column('meta_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=True),
        sa.Column('updated_at', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['file_id'], ['file.id'], ),
        sa.ForeignKeyConstraint(['parent_session_id'], ['image_sessions.id'], )
    )
    
    # Create indexes
    op.create_index('ix_image_sessions_chat_user_created', 'image_sessions', ['chat_id', 'user_id', 'created_at'])
    op.create_index('ix_image_sessions_chat_id', 'image_sessions', ['chat_id'])
    op.create_index('ix_image_sessions_user_id', 'image_sessions', ['user_id'])

def downgrade():
    """Drop image_sessions table"""
    op.drop_index('ix_image_sessions_user_id', 'image_sessions')
    op.drop_index('ix_image_sessions_chat_id', 'image_sessions')
    op.drop_index('ix_image_sessions_chat_user_created', 'image_sessions')
    op.drop_table('image_sessions')
