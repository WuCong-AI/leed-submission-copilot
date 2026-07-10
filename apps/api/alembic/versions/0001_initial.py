"""initial LEED submission copilot schema"""
from alembic import op
from app.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)

def downgrade():
    Base.metadata.drop_all(op.get_bind())
