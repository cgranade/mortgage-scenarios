import numpy as np
from math import ceil
from dataclasses import dataclass, replace

from pint import UnitRegistry
from pint.definitions import UnitDefinition
from pint.converters import ScaleConverter

from typing import Callable, Tuple, Optional

ureg = UnitRegistry()

ureg.define(UnitDefinition('percent', None, (), ScaleConverter(1 / 100)))
ureg.load_definitions('units.txt')
Q = ureg.Quantity


@dataclass
class Mortgage(object):
    loan_amount: Q = Q(500_000, 'dollars')
    home_value: Q = Q(600_000, 'dollars')
    duration: Q = Q(10, 'years')
    base_rate: Q = Q(4, 'percent') / Q(1, 'year')
    base_closing_costs: Q = Q(5_000, 'dollars')

    #: The cost as a ratio of the loan amount for each point.
    #: See the CFPB for more detail:
    #:
    #:     https://www.consumerfinance.gov/ask-cfpb/what-are-discount-points-and-lender-credits-and-how-do-they-work-en-136/
    #:
    cost_per_point: Q = Q(1, 'percent / dp')

    #: The amount by which each point reduces the base annual interest
    #: rate.
    rate_reduction_per_point: Q = Q(0.125, 'percent / (year * dp)')

    def effective_rate(self, n_points: Q) -> Q:
        return self.base_rate - self.rate_reduction_per_point * n_points

    def actual_closing_costs(self, n_points: Q) -> Q:
        return self.base_closing_costs + self.cost_per_point * self.loan_amount * n_points

    @property
    def down_payment(self):
        return self.home_value - self.loan_amount

    @property
    def n_payments(self) -> int:
        return ceil(self.duration / Q(1, 'month'))

    def base_payment(self, n_points: Q) -> Q:
        # Calculate the monthly interest.
        monthly_rate = self.effective_rate(n_points).to('percent / month')
        compounding = (1 + monthly_rate.to('dimensionless / month').magnitude) ** self.n_payments
        return (self.loan_amount * monthly_rate * compounding / (compounding - 1)).to('dollars / month')

    def payment_schedule(self, n_points: Q, overpayment_strategy: Optional[Callable[["Mortgage"], Q]] = None):
        if overpayment_strategy is None:
            overpayment_strategy = lambda mortgage: Q(0, 'dollars / month')

        remaining = self
        base = self.base_payment(n_points) * Q(1, 'month')

        # Cut off at some small number of dollars (10¢) to avoid rounding errors.
        while remaining.loan_amount > Q(0.1, 'dollars'):
            interest = (
                remaining.loan_amount *
                Q(1, 'month') *
                self.effective_rate(n_points).to('percent / month')
            )
            payment = base + overpayment_strategy(remaining) * Q(1, 'month') 
            # Don't pay negative amounts.
            principal = payment - interest
            if principal > remaining.loan_amount:
                payment = principal + interest
            remaining = replace(self, loan_amount=remaining.loan_amount - principal)
            yield remaining, payment

    def total_cost(self, n_points: Q, overpayment_strategy: Optional[Callable[["Mortgage"], Q]] = None) -> Tuple[Q, Q]:
        payment_schedule = list(self.payment_schedule(n_points, overpayment_strategy))
        return self.down_payment + self.actual_closing_costs(n_points) + sum(
            payment for remaining, payment in payment_schedule
        ), Q(len(payment_schedule), 'month')

