import torch
from torch.optim import Adam
import numpy as np
from Networks import FFN, Net_DGM, DGM_Layer
from matplotlib import pyplot as plt
from E1_1 import SolveLQR

def get_gradient(output, x):
    grad = torch.autograd.grad(output, x, grad_outputs=torch.ones_like(output), create_graph=True, retain_graph=True, only_inputs=True)[0]
    return grad

sigma = torch.diag(torch.tensor([0.05, 0.05]))
sig = torch.mm(sigma, sigma.T)

# def get_laplacian(grad, x):
#     v1 = grad[:,0].view(-1,1)
#     grad21 = \
#         torch.autograd.grad(v1, x, grad_outputs=torch.ones_like(v1), only_inputs=True, create_graph=True, retain_graph=True)[0]
#     v2 = grad[:,1].view(-1,1)
#     grad22 = \
#         torch.autograd.grad(v2, x, grad_outputs=torch.ones_like(v2), only_inputs=True, create_graph=True, retain_graph=True)[0]
#     grad21 = grad21.unsqueeze(2)
#     grad22 = grad22.unsqueeze(2)
#     tr_hess = torch.matmul(sig.double(), torch.cat((grad21, grad22), 2).double()).diagonal(offset=0, dim1=-1, dim2=-2).sum(-1)
#     return tr_hess.unsqueeze(1)

def get_laplacian(grad, x):
    # hessian actually but anyway
    hess_diag = []
    for d in range(x.shape[1]):
        v = grad[:,d].view(-1,1)
        grad2 = torch.autograd.grad(v,x,grad_outputs=torch.ones_like(v), only_inputs=True, create_graph=True, retain_graph=True)[0]
        hess_diag.append(grad2[:,d].view(-1,1))
    hess_diag = torch.cat(hess_diag,1)
    laplacian = hess_diag.sum(1, keepdim=True)
    return laplacian


class AgentDP:

    def __init__(self, batch_size, H, M, R, C, D, sigma, T,
                 learning_rate_critic,
                 learning_rate_policy):
        '''
        :param batch_size: sample size each iteration/improvement
        :param H: matrix H
        :param M: matrix M
        :param C: matrix C
        :param D: matrix D
        :param learning_rate_critic: learning rate for value function network
        :param learning_rate_policy: learning rate for policy function network
        '''
        self.policy_net = FFN([3, 100, 2])
        self.critic_net = Net_DGM(2, 100, activation = 'LogSigmoid')

        self.batch_size = batch_size
        self.H = H
        self.M = M
        self.R = R
        self.C = C
        self.D = D
        self.sigma = sigma
        self.tr = torch.mm(self.sigma, self.sigma.T).trace()
        self.T = T

        self.optim_critic = Adam(self.critic_net.parameters(), lr = learning_rate_critic)
        self.optim_policy = Adam(self.policy_net.parameters(), lr = learning_rate_policy)

        self.loss_fn = torch.nn.MSELoss(reduction='mean')

    def policy_improvement(self, t, x):
        '''
        :param t: one episode of t with batch size
        :param x: one episode of x with batch size
        :return: loss of critic network
        '''

        u_of_tx = self.critic_net(t, x)
        grad_u_x = get_gradient(u_of_tx, x)
        alpha = self.policy_net(t, x)

        self.optim_policy.zero_grad()

        H_loss = (torch.mul(torch.matmul(input_domain, self.H.T), grad_u_x)
                 + torch.mul(torch.matmul(alpha, self.M.T), grad_u_x)
                 + torch.mul(torch.matmul(x, self.C), x)
                 + torch.mul(torch.matmul(alpha, self.D), alpha)
                 ).sum(dim = 1)

        H_loss = H_loss.mean(dim = 0)

        H_loss.backward(retain_graph = True)
        self.optim_policy.step()
        self.optim_policy.zero_grad()
        return {'Hamiltonian loss:': H_loss.item()}

    def policy_evaluate(self, t, x):
        '''
        :param t: one episode of t with batch size
        :param x: one episode of x with batch size
        :return: loss of policy network
        '''

        alpha = self.policy_net(t, x)

        u_of_tx = self.critic_net(t, x)
        grad_u_x = get_gradient(u_of_tx, x)
        grad_u_t = get_gradient(u_of_tx, t)
        laplacian = get_laplacian(grad_u_x, x)

        target_functional = torch.zeros_like(u_of_tx)

        self.optim_critic.zero_grad()
        pde = grad_u_t + 0.5 * self.tr * laplacian \
              + (torch.mul(torch.matmul(input_domain, self.H.T), grad_u_x)
                 + torch.mul(torch.matmul(alpha, self.M.T), grad_u_x)
                 + torch.mul(torch.matmul(x, self.C), x)
                 + torch.mul(torch.matmul(alpha, self.D), alpha)
                 ).sum(dim = 1).unsqueeze(1)

        MSE_functional = self.loss_fn(pde, target_functional)

        input_terminal = x
        t_terminal = torch.ones(self.batch_size, 1) * self.T

        u_of_tx = self.critic_net(t_terminal, input_terminal)
        target_terminal = torch.mul(torch.matmul(x, self.R), x).sum(dim = 1).unsqueeze(1)
        MSE_terminal = self.loss_fn(u_of_tx, target_terminal)

        B_loss = MSE_functional + MSE_terminal
        print(B_loss)
        B_loss.backward(retain_graph=True)
        self.optim_critic.step()
        self.optim_critic.zero_grad()
        return {'Bellman Loss:': B_loss.item()}

H = torch.eye(2).double()
M = torch.eye(2).double()
R = torch.eye(2).double()
C = torch.eye(2).double() * 0.1
D = torch.eye(2).double() * 0.1
T = 1
sigma = torch.diag(torch.tensor([0.05, 0.05]))


# Initialize the dynamic programming agent
agent = AgentDP(10000, H, M, R, C, D, sigma, T, 0.001, 0.001)

# Example of usage of update function
t = torch.rand(10000, 1, requires_grad=True).double()
input_domain = (torch.rand(10000, 2, requires_grad=True) - 0.5)*6
input_domain = input_domain.double()
# print(agent.policy_improvement(t,input_domain))
u_of_tx = agent.critic_net(t, input_domain)
grad_u_x = get_gradient(u_of_tx, input_domain)
grad_u_t = get_gradient(u_of_tx, t)
alpha = agent.policy_net(t, input_domain)
# print(agent.policy_evaluate(t, input_domain))

H = np.identity(2)
M = np.identity(2)
R = np.identity(2)
C = 0.1*np.identity(2)
D = 0.1*np.identity(2)
SIG = np.diag([0.05, 0.05])
t_grid = torch.from_numpy(np.linspace(0, 1, 10000))

t0 = torch.tensor([0]).float()
x0 = torch.tensor([1, 1]).float()

standard_sol = SolveLQR(H, M, C, D, R, SIG, t_grid)
standard_v = standard_sol.get_value(t0, x0)
standard_a = standard_sol.get_controller(t0, x0).squeeze()
print(standard_v)


def train_DP(Agent, criteria, max_steps, example = False):
    '''
    :param Agent:
    :param criteria:
    :param max_steps:
    :return:
    '''
    l2 = torch.nn.MSELoss(reduction='mean')
    error = criteria * 1e6
    t = torch.rand(10000, 1, requires_grad=True).double()
    x = (torch.rand(10000, 2, requires_grad=True) - 0.5) * 6
    x = x.double()
    step = 1
    error_list_v = []
    error_list_a = []

    while (error > criteria) & (step < max_steps):
        value_last = Agent.critic_net(t, x).squeeze(1)
        Agent.policy_evaluate(t, x)
        Agent.policy_improvement(t, x)
        value_improved = Agent.critic_net(t, x).squeeze(1)
        error = l2(value_improved, value_last).item()
        print({f'Step {step}': error})
        step += 1

        # Example
        t_test = torch.tensor([[0]]).double()
        x_test = torch.tensor([[1, 1]]).double()
        value_test = Agent.critic_net(t_test, x_test)
        alpha_test = Agent.policy_net(t_test, x_test).squeeze()
        error_a = torch.norm(alpha_test-standard_a, p=2, dim=0).item()
        l2_a = torch.norm(standard_a, p=2, dim=0).detach().item()
        error_list_v.append((torch.abs(value_test-standard_v)/standard_v).item())
        error_list_a.append(error_a)

    if example:
        plt.plot(np.arange(0, step - 1), error_list_v, label = 'relative error of value')
        plt.plot(np.arange(0, step - 1), error_list_a, label = 'absolute error of alpha')
        plt.xlabel("Iterations", fontsize = 18)
        plt.ylabel("Error", fontsize = 18)
        plt.xticks(fontsize = 15)
        plt.yticks(fontsize = 15)
        plt.legend()
        plt.show()

    return value_test.item()

t_dp, x_dp, value_dp = train_DP(agent, 1e-5, 800, example = True)

