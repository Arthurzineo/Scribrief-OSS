from .membership import UserMembership as UserMembership
from .sector import Sector as Sector
from .sector_key import SectorAICredential as SectorAICredential
from .sector_prompt import SectorAIPrompt as SectorAIPrompt

# Import compatibility for existing local scripts/tests; the model/table is generic.
SectorOpenAIKey = SectorAICredential
