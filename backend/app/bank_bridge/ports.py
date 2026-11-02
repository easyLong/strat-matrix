"""Only these methods may reference bank-owned data or production capabilities."""

from typing import Protocol
from .contracts import (Account, AccountQuery, DemandReceipt, EffectivePlacement,
                        EffectivePlacementQuery, MarketingContent, MarketingDemand,
                        MarketingQuery, Page, ProductionQuery, ProductionRecord,
                        Topic, TopicQuery, MarketingStatusQuery, MarketingProductionRecord)


class IntegrationUnavailable(Exception):
    """Unfilled capability; never turn this into a successful empty result."""


class DataContractError(Exception):
    """Provider response does not satisfy the agreed contract."""


class BankSource(Protocol):
    def accounts(self, query: AccountQuery) -> Page[Account]: ...
    def topics(self, query: TopicQuery) -> Page[Topic]: ...
    def marketing_contents(self, query: MarketingQuery) -> Page[MarketingContent]: ...
    def effective_marketing(self, query: EffectivePlacementQuery) -> list[EffectivePlacement]: ...


class BankProduction(Protocol):
    def production_results(self, query: ProductionQuery) -> list[ProductionRecord]: ...

    # Marketing demand execution is also owned by the bank, without planner slot allocation.
    def marketing_results(self, query: MarketingStatusQuery) -> list[MarketingProductionRecord]: ...
