#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2021 The OpenRL Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""""""

import torch
import torch.nn as nn

from openrl.buffers.utils.util import get_critic_obs_space
from openrl.modules.networks.base_value_network import BaseValueNetwork
from openrl.modules.networks.utils.cnn import CNNBase
from openrl.modules.networks.utils.mix import MIXBase
from openrl.modules.networks.utils.mlp import MLPBase, MLPLayer
from openrl.modules.networks.utils.popart import PopArt
from openrl.modules.networks.utils.rnn import RNNLayer
from openrl.modules.networks.utils.util import init
from openrl.utils.util import check_v2 as check


class ValueNetwork(BaseValueNetwork):
    def __init__(
        self,
        cfg,
        input_space,
        action_space=None,
        use_half=False,
        device=torch.device("cpu"),
        extra_args=None,
    ):
        super(ValueNetwork, self).__init__(cfg, device)

        self._use_transformer = True

        self.hidden_size = cfg.hidden_size
        self._use_orthogonal = cfg.use_orthogonal
        self._activation_id = cfg.activation_id
        self._use_naive_recurrent_policy = cfg.use_naive_recurrent_policy
        self._use_recurrent_policy = cfg.use_recurrent_policy
        self._use_influence_policy = cfg.use_influence_policy
        self._use_popart = cfg.use_popart
        self._influence_layer_N = cfg.influence_layer_N
        self._recurrent_N = cfg.recurrent_N
        self.tpdv = dict(dtype=torch.float32, device=device)

        init_method = [nn.init.xavier_uniform_, nn.init.orthogonal_][
            self._use_orthogonal
        ]

        critic_obs_shape = get_critic_obs_space(input_space)

        self.tf_max_len = 60 # cfg.tf_max_len

        if self._use_transformer:

            import transformers
            config = transformers.GPT2Config(
                n_embd=self.hidden_size,
                n_positions=400, # TODO: max_episode_len
                n_layer=3,
                n_head=1,
                n_inner=64,
                activation_function="tanh",
            )
            self.transformer = transformers.GPT2Model(config)
            self.transformer = torch.nn.DataParallel(self.transformer)
            # self.transformer = transformers.GPT2Model.from_pretrained(
            #     'gpt2', config=config
            # )

            obs_dim = critic_obs_shape[0]
            self.embed_obs = torch.nn.Linear(obs_dim, self.hidden_size)
            self.embed_ln = nn.LayerNorm(self.hidden_size)

            self._mixed_obs = ("Dict" in critic_obs_shape.__class__.__name__)
        
        else:
            if "Dict" in critic_obs_shape.__class__.__name__:
                self._mixed_obs = True
                self.base = MIXBase(
                    cfg, critic_obs_shape, cnn_layers_params=cfg.cnn_layers_params
                )
            else:
                self._mixed_obs = False
                self.base = (
                    CNNBase(cfg, critic_obs_shape)
                    if len(critic_obs_shape) == 3
                    else MLPBase(
                        cfg,
                        critic_obs_shape,
                        use_attn_internal=True,
                        use_cat_self=cfg.use_cat_self,
                    )
                )

            input_size = self.base.output_size

            if self._use_naive_recurrent_policy or self._use_recurrent_policy:
                self.rnn = RNNLayer(
                    input_size,
                    self.hidden_size,
                    self._recurrent_N,
                    self._use_orthogonal,
                    rnn_type=cfg.rnn_type,
                )
                input_size = self.hidden_size

            if self._use_influence_policy:
                self.mlp = MLPLayer(
                    critic_obs_shape[0],
                    self.hidden_size,
                    self._influence_layer_N,
                    self._use_orthogonal,
                    self._activation_id,
                )
                input_size += self.hidden_size

        def init_(m):
            return init(m, init_method, lambda x: nn.init.constant_(x, 0))

        if self._use_popart:
            self.v_out = init_(PopArt(self.hidden_size, 1, device=device))
        else:
            self.v_out = init_(nn.Linear(self.hidden_size, 1))

        self.to(device)

    def forward(self, critic_obs, rnn_states, masks, env_step):
        if self._mixed_obs:
            for key in critic_obs.keys():
                critic_obs[key] = check(critic_obs[key]).to(**self.tpdv)
        else:
            critic_obs = check(critic_obs).to(**self.tpdv)

        if self._use_transformer:

            batch_size, seq_length, _ = critic_obs.shape

            env_step = env_step.squeeze(-1)
            env_step = check(env_step).to(**self.tpdv).long()

            attention_mask = torch.zeros([batch_size, self.tf_max_len])
            attention_mask = check(attention_mask).to(**self.tpdv)
            for data_id in range(batch_size):
                attention_mask[data_id,-env_step[data_id,-1]-1:] = 1.

            critic_features = self.embed_obs(critic_obs)
            critic_features = self.embed_ln(critic_features)
            transformer_outputs = self.transformer(
                inputs_embeds=critic_features,
                attention_mask=attention_mask,
                position_ids=env_step,
            )
            critic_features = transformer_outputs['last_hidden_state']
            critic_features = critic_features[:,-1]
        else:

            rnn_states = check(rnn_states).to(**self.tpdv)
            masks = check(masks).to(**self.tpdv)

            critic_features = self.base(critic_obs)

            if self._use_naive_recurrent_policy or self._use_recurrent_policy:
                critic_features, rnn_states = self.rnn(critic_features, rnn_states, masks)

            if self._use_influence_policy:
                mlp_critic_obs = self.mlp(critic_obs)
                critic_features = torch.cat([critic_features, mlp_critic_obs], dim=1)

        values = self.v_out(critic_features)

        return values, None
