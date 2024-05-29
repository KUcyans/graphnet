"""Standard model class(es)."""

from typing import Any, Dict, List, Optional, Union, Type
import torch
from torch import Tensor
from torch_geometric.data import Data
from torch.optim import Adam

from graphnet.models.gnn.gnn import GNN
from .easy_model import EasySyntax
from graphnet.models.task import StandardFlowTask
from graphnet.models.graphs import GraphDefinition
from graphnet.models.utils import get_fields


class NormalizingFlow(EasySyntax):
    """A model for building (conditional) normalizing flows in GraphNeT.

    This model relies on `jammy_flows` for building and evaluating
    normalizing flows.
    https://thoglu.github.io/jammy_flows/usage/introduction.html
    for details.
    """

    def __init__(
        self,
        graph_definition: GraphDefinition,
        target_labels: str,
        backbone: GNN = None,
        condition_on: Union[str, List[str], None] = None,
        flow_layers: str = "gggt",
        optimizer_class: Type[torch.optim.Optimizer] = Adam,
        optimizer_kwargs: Optional[Dict] = None,
        scheduler_class: Optional[type] = None,
        scheduler_kwargs: Optional[Dict] = None,
        scheduler_config: Optional[Dict] = None,
    ) -> None:
        """Construct `NormalizingFlow`."""
        # Checks
        if (backbone is not None) & (condition_on is not None):
            # If user wants to condition on both
            raise ValueError(
                f"{self.__class__.__name__} got values for both "
                "`backbone` and `condition_on`, but can only"
                "condition on one of those. Please specify just "
                "one of these arguments."
            )

        # Handle args
        if backbone is not None:
            assert isinstance(backbone, GNN)
            hidden_size = backbone.nb_outputs
        elif condition_on is not None:
            if isinstance(condition_on, str):
                condition_on = [condition_on]
            hidden_size = len(condition_on)
        else:
            hidden_size = None

        # Build Flow Task
        task = StandardFlowTask(
            hidden_size=hidden_size,
            flow_layers=flow_layers,
            target_labels=target_labels,
        )

        # Base class constructor
        super().__init__(
            tasks=task,
            optimizer_class=optimizer_class,
            optimizer_kwargs=optimizer_kwargs,
            scheduler_class=scheduler_class,
            scheduler_kwargs=scheduler_kwargs,
            scheduler_config=scheduler_config,
        )

        # Member variable(s)
        self._graph_definition = graph_definition
        self.backbone = backbone
        self._condition_on = condition_on

    def forward(self, data: Union[Data, List[Data]]) -> Tensor:
        """Forward pass, chaining model components."""
        if isinstance(data, Data):
            data = [data]
        x_list = []
        for d in data:
            if self.backbone is not None:
                x = self._backbone(d)
            elif self._condition_on is not None:
                assert isinstance(self._condition_on, list)
                x = get_fields(data=d, fields=self._condition_on)
            else:
                # Unconditional flow
                x = None
            x = self._tasks[0](x, d)
            x_list.append(x)
        x = torch.cat(x_list, dim=0)
        return x

    def _backbone(
        self, data: Union[Data, List[Data]]
    ) -> List[Union[Tensor, Data]]:
        assert self.backbone is not None
        return self.backbone(data)

    def shared_step(self, batch: List[Data], batch_idx: int) -> Tensor:
        """Perform shared step.

        Applies the forward pass and the following loss calculation, shared
        between the training and validation step.
        """
        loss = self(batch)
        return torch.mean(loss, dim=0)

    def validate_tasks(self) -> None:
        """Verify that self._tasks contain compatible elements."""
        accepted_tasks = StandardFlowTask
        for task in self._tasks:
            assert isinstance(task, accepted_tasks)
