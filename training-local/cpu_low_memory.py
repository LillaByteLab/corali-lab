"""FP32 arithmetic with frozen BF16 weights; recast only during backward."""
import torch,types

class FrozenLinear(torch.autograd.Function):
    @staticmethod
    def forward(ctx,x,weight,bias):
        if weight.requires_grad or (bias is not None and bias.requires_grad):
            raise ValueError('This operation supports frozen base weights only.')
        ctx.save_for_backward(weight);ctx.input_dtype=x.dtype
        return torch.nn.functional.linear(x.float(),weight.float(),None if bias is None else bias.float()).to(x.dtype)
    @staticmethod
    def backward(ctx,gradient):
        weight,=ctx.saved_tensors
        return torch.matmul(gradient.float(),weight.float()).to(ctx.input_dtype),None,None

def install(model):
    def forward(self,x):return FrozenLinear.apply(x,self.weight,self.bias)
    for module in model.modules():
        if isinstance(module,torch.nn.Linear):module.forward=types.MethodType(forward,module)

def verify():
    torch.manual_seed(21)
    for dtype in (torch.float32,torch.bfloat16):
        x=torch.randn(2,11,32,dtype=dtype,requires_grad=True);y=x.detach().clone().requires_grad_()
        w=torch.randn(17,32,dtype=torch.bfloat16);b=torch.randn(17,dtype=torch.bfloat16)
        a=FrozenLinear.apply(x,w,b);reference=torch.nn.functional.linear(y.float(),w.float(),b.float()).to(dtype)
        assert torch.equal(a,reference)
        a.float().square().sum().backward();reference.float().square().sum().backward()
        assert torch.equal(x.grad,y.grad)
    print('FP32/BF16 forward and input gradients match standard PyTorch exactly.')

if __name__=='__main__':verify()
