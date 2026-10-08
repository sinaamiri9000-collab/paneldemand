"""Restricted, regime-varying slope layer; native QUAIDS algebra is reused.

Only selected beta/gamma/lambda blocks vary. Every regime retains adding up,
homogeneity and symmetry. Demographic translations, censoring and CF loadings
are shared; these are deliberately restricted stability tests.
"""
from dataclasses import dataclass
import numpy as np
from panel_core import PanelCore
from pyquaidsce.params import unpack
from pyquaidsce.model import fitted_shares, _inner
from pyquaidsce.jacfree import jacobian_free


@dataclass
class RegimeSpec:
    nshift: int
    neqn: int
    common_base: int
    ncontrast: int
    slope_width: int

    @property
    def nbase(self):
        return self.common_base + self.ncontrast*self.slope_width

    @property
    def n_free(self):
        return self.nbase + self.nshift*(self.neqn-1)

    @property
    def n_eq_estimated(self):
        return self.neqn


class RegimeCore(PanelCore):
    def __init__(self, data, Z, regimes, blocks=('beta','gamma','lambda')):
        super().__init__(data.lnp,data.lnexp,data.shares,data.cdf,data.pdf,
                         data.control_function,Z,data.a0)
        self.regimes=np.asarray(regimes,dtype=int)
        values=np.unique(self.regimes)
        if not np.array_equal(values,np.arange(len(values))):
            raise ValueError('Regime codes must be consecutive from zero')
        self.blocks=tuple(blocks)
        if not self.blocks or any(b not in ('beta','gamma','lambda') for b in blocks):
            raise ValueError('Only beta/gamma/lambda slope contrasts supported')
        self.common_base=self.spec.nbase
        self.slope_indices=np.concatenate([
            np.arange(self.base_slices[b].start,self.base_slices[b].stop) for b in blocks])
        self.slope_width=len(self.slope_indices)
        self.spec=RegimeSpec(self.Z.shape[1],self.spec.neqn,self.common_base,
                             len(values)-1,self.slope_width)

    def contrast_slice(self, regime):
        start=self.common_base+(regime-1)*self.slope_width
        return slice(start,start+self.slope_width)

    def unpack(self,theta,regime=0):
        native=self.offset+self.T@theta[:self.common_base]
        if regime:
            native=native+self.T[:,self.slope_indices]@theta[self.contrast_slice(regime)]
        eta=theta[self.spec.nbase:].reshape(self.spec.nshift,self.spec.neqn-1)@self.B.T
        return native,eta

    def warm_start(self, common_theta):
        common_theta=np.asarray(common_theta)
        assert len(common_theta)==self.common_base+self.spec.nshift*(self.spec.neqn-1)
        theta=np.zeros(self.spec.n_free)
        theta[:self.common_base]=common_theta[:self.common_base]
        theta[self.spec.nbase:]=common_theta[self.common_base:]
        return theta

    def _pieces(self,theta,rows):
        d=self.data.subset(rows)
        codes=self.regimes[rows]
        _,eta=self.unpack(theta)
        shift=self.Z[rows]@eta
        d.lnexp=d.lnexp-np.einsum('ti,ti->t',d.lnp,shift)
        for code in np.unique(codes):
            mask=codes==code
            nt,_=self.unpack(theta,int(code))
            yield int(code),mask,nt,d.subset(mask),shift[mask]

    def fitted(self,theta,rows=slice(None)):
        n=len(self.regimes[rows])
        result=np.zeros((n,self.spec.neqn))
        for code,mask,nt,d,shift in self._pieces(theta,rows):
            result[mask]=fitted_shares(nt,d,self.native)+d.cdf*shift
        return result

    def derivative_blocks(self,theta,rows):
        n=len(self.regimes[rows]);m=self.spec.neqn
        J=np.zeros((n,m,self.spec.nbase));H=np.zeros((n,m,m-1))
        for code,mask,nt,d,shift in self._pieces(theta,rows):
            base=jacobian_free(nt,d,self.native,self.cache)@self.T
            J[mask,:,:self.common_base]=base
            if code:
                J[mask,:,self.contrast_slice(code)]=base[:,:,self.slope_indices]
            inn=_inner(unpack(nt,self.native),d,self.native)
            H[mask]=d.cdf[:,:,None]*(self.B[None,:,:]-
                inn.S[:,:,None]*(d.lnp@self.B)[:,None,:])
        return J,H
