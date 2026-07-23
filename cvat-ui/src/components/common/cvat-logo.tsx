// Copyright (C) CVAT.ai Corporation
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import { CombinedState } from 'reducers';

function CVATLogo(): JSX.Element {
    const logo = useSelector((state: CombinedState) => state.about.server.logoURL);

    return (
        <div className='cvat-logo-icon'>
            <Link to='/' aria-label='Go to the main page'>
                <img src={logo} alt='CVAT Logo' />
            </Link>
        </div>
    );
}

export default React.memo(CVATLogo);
